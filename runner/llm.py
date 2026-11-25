"""
Minimal litellm-based LLM client, Ollama-only.

Mirrors the shape of the multi-provider client in
Agentic-Pentesting-Orchestrator/runner/agent_runner/llm.py, trimmed down to
just the provider that matters here: a local (or self-hosted remote) Ollama
server, called via litellm's `ollama_chat/` prefix (POST /api/chat, native
tool-calling support).

Point OLLAMA_API_BASE at a remote server if you're not running Ollama on
localhost. No API key required by default.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field

import litellm

logger = logging.getLogger(__name__)

# Suppress litellm verbose output unless debugging
litellm.set_verbose = os.getenv("LLM_DEBUG", "0") == "1"


@dataclass
class LlmConfig:
    api_base: str = field(default_factory=lambda: os.getenv("OLLAMA_API_BASE") or "http://localhost:11434")
    model: str = field(default_factory=lambda: os.getenv("LLM_MODEL") or "qwen2.5:14b")
    api_key: str = field(default_factory=lambda: os.getenv("OLLAMA_API_KEY", ""))
    context_window: int = field(default_factory=lambda: int(os.getenv("LLM_CONTEXT_WINDOW", "32768")))
    max_tokens: int = field(default_factory=lambda: int(os.getenv("LLM_MAX_TOKENS", "8192")))
    # Hybrid reasoning models (gemma4, qwen3, ...) can burn the whole max_tokens
    # budget on hidden chain-of-thought before emitting an actual tool call/answer
    # (observed: 80s+ stall then empty final message), and some quantizations leak
    # raw <|channel|>/<think> template tokens into tool-call argument text instead
    # of keeping them in a separate reasoning channel. Disabled by default.
    disable_thinking: bool = field(default_factory=lambda: os.getenv("LLM_DISABLE_THINKING", "1") == "1")
    retry_attempts: int = field(default_factory=lambda: max(1, int(os.getenv("LLM_RETRY_ATTEMPTS", "3"))))
    retry_base_delay: float = field(default_factory=lambda: max(0.1, float(os.getenv("LLM_RETRY_BASE_DELAY", "2"))))


class LlmClient:
    """
    Thin wrapper around litellm.completion() targeting a local Ollama server.

    Example::

        client = LlmClient(LlmConfig())
        response = client.complete(
            messages=[{"role": "user", "content": "Hello"}],
            tools=[...],  # optional function-calling tools
        )
    """

    def __init__(self, config: LlmConfig | None = None) -> None:
        self.config = config or LlmConfig()

    @property
    def model(self) -> str:
        # ollama_chat/ (vs ollama/) hits /api/chat and supports native tool calling
        return f"ollama_chat/{self.config.model}"

    def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> litellm.ModelResponse:
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens or self.config.max_tokens,
            "temperature": temperature,
            "api_base": self.config.api_base,
            # Ollama sizes its KV cache off num_ctx; without this Ollama silently
            # truncates context to its 2048-token default regardless of the model's
            # real window, which breaks long agent tool-call transcripts fast.
            "num_ctx": self.config.context_window,
        }
        if self.config.api_key:
            kwargs["api_key"] = self.config.api_key

        if self.config.disable_thinking:
            # litellm maps reasoning_effort -> Ollama's native "think" request field;
            # any value outside {low, medium, high} resolves to think=False for
            # non-gpt-oss models (see litellm ollama/chat/transformation.py).
            kwargs["reasoning_effort"] = "off"

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        return self._with_retries(lambda: litellm.completion(**kwargs))

    def _with_retries(self, request):
        for attempt in range(1, self.config.retry_attempts + 1):
            try:
                return request()
            except Exception as exc:
                if not self._is_transient(exc) or attempt == self.config.retry_attempts:
                    raise
                delay = self.config.retry_base_delay * (2 ** (attempt - 1))
                logger.warning(
                    "Transient LLM failure (%s), retrying in %.1fs (%d/%d)",
                    type(exc).__name__, delay, attempt, self.config.retry_attempts,
                )
                time.sleep(delay)

    @staticmethod
    def _is_transient(exc: Exception) -> bool:
        status = getattr(exc, "status_code", None)
        if status in {408, 409, 429, 500, 502, 503, 504}:
            return True
        text = str(exc).lower()
        name = type(exc).__name__.lower()
        return any(token in name or token in text for token in (
            "timeout", "connect", "temporarily unavailable", "unavailable",
        ))
