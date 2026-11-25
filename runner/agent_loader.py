"""
Loads agent persona prompts from the agents/ directory tree.

Each agent's system prompt is assembled from:
  - agents/shared/constraints.md    (rules every agent must follow)
  - agents/shared/output-schemas.md (loot/ file YAML schemas)
  - agents/shared/tooling.md        (full CLI tool inventory)
  - agents/<AgentName>/definition.md (the agent's own responsibilities)
"""

from __future__ import annotations

import os
from pathlib import Path

# Small/local models pay for every token of the system prompt on every single
# turn. tooling.md is a big flat reference table most agents only need slices
# of (e.g. ReconAgent never needs PWN/crypto tooling) - LLM_SLIM_PROMPT=1 drops
# it entirely and leans on the model's own knowledge of common CLI tool names.
SLIM_PROMPT = os.getenv("LLM_SLIM_PROMPT", "0") == "1"

AGENT_NAMES = [
    "OrchestratorAgent", "HTBAgent", "ReconAgent", "InfraAgent", "WebTestAgent",
    "APIAgent", "JSLibAgent", "ExploitAgent", "PrivEscAgent", "FlagAgent",
    "LoggerAgent", "ValidatorAgent", "PWNAgent", "CryptoAgent", "ForensicsAgent",
]


class AgentLoader:
    def __init__(self, agents_dir: Path):
        self.agents_dir = agents_dir
        self._shared_cache: str | None = None

    def _shared_context(self) -> str:
        if self._shared_cache is None:
            shared_dir = self.agents_dir / "shared"
            names = ("constraints.md", "output-schemas.md") if SLIM_PROMPT else (
                "constraints.md", "output-schemas.md", "tooling.md",
            )
            parts = []
            for name in names:
                path = shared_dir / name
                if path.exists():
                    parts.append(f"## shared/{name}\n\n{path.read_text()}")
            self._shared_cache = "\n\n---\n\n".join(parts)
        return self._shared_cache

    def system_prompt(self, agent_name: str, db_enabled: bool = False) -> str:
        if agent_name not in AGENT_NAMES:
            raise ValueError(f"Unknown agent: {agent_name!r} (known: {AGENT_NAMES})")
        definition_path = self.agents_dir / agent_name / "definition.md"
        definition = definition_path.read_text()

        tools_desc = "run_command, read_file, write_file, list_dir, delegate_agent"
        completion_rule = (
            "Only stop calling tools (i.e. respond with plain text and no tool call) "
            "once your objective for this invocation is complete, blocked with a clear "
            "written blocker, or you need the operator's input on something no agent "
            "can decide (e.g. missing credentials)."
        )
        db_rules = ""
        if db_enabled:
            tools_desc += ", get_facts, set_fact, record_finding, list_findings, create_subtask, complete_task"
            completion_rule = (
                "You MUST call complete_task(summary, status) when — and only when — your "
                "current task is done, blocked, or failed. Do not just stop calling tools and "
                "go quiet; that leaves no record of what happened."
            )
            db_rules = (
                "\n\n## Before you enumerate/scan anything\n\n"
                "1. Call get_facts and list_findings FIRST. Other tasks/agents may have already "
                "confirmed exactly what you're about to go look for. Re-running recon that's "
                "already been done wastes time and burns your iteration budget for nothing.\n"
                "2. Only run a new scan/enumeration command if it answers a question the existing "
                "facts/findings don't already answer.\n"
                "3. After you confirm something real (an open port, a working endpoint, a "
                "vulnerability, a credential), call record_finding immediately — don't wait until "
                "the end, and don't rely on it staying in your own context.\n"
                "4. If you notice yourself running the same category of command (nmap, ffuf, "
                "gobuster, etc.) more than 5-6 times in this one task, STOP. Check list_findings — "
                "you almost certainly have enough to act on or hand off already."
            )

        grounding_rule = (
            "\n\n## Grounding — do not hallucinate\n\n"
            "Only state facts, findings, ports, endpoints, credentials, or flags that you "
            "directly observed in actual tool output earlier in this conversation. If you're "
            "not sure whether you actually ran a command or just planned to, run it (or check "
            "get_facts/list_findings/read_file) before claiming the result. Never write a "
            "recon_results.yaml, loot.yaml, or flags.yaml entry that isn't backed by real output "
            "you can point to."
        )

        return (
            f"You are {agent_name}, a specialist in an autonomous multi-agent CTF "
            "pentesting stack targeting a single Hack The Box (or similar) machine "
            "over an already-connected VPN. You operate by calling tools "
            f"({tools_desc}) — there is no human in the loop watching a chat UI, so "
            "act autonomously and keep driving toward the goal instead of asking the "
            "operator questions.\n\n"
            f"{completion_rule}"
            f"{db_rules}"
            f"{grounding_rule}\n\n"
            f"## Your definition: {agent_name}\n\n{definition}\n\n"
            "---\n\n"
            "# Shared rules and reference material\n\n"
            f"{self._shared_context()}"
        )
