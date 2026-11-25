"""
The agent tool-calling loop: feeds a persona system prompt + running message
history into the Ollama LLM, executes whatever tools it calls, feeds the
results back, and repeats until the model stops calling tools.

`delegate_agent` lets any agent (mainly OrchestratorAgent) spin up another
agent persona as a nested AgentRunner sharing the same workspace/loot dir —
this is the standalone-runner equivalent of the "@ReconAgent, do X" hand-off
described in the agent definition docs, since there's no chat UI here to do
that hand-off for us.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from pathlib import Path

from .agent_loader import AGENT_NAMES, AgentLoader
from .llm import LlmClient, LlmConfig
from .tools import BASE_TOOL_IMPLS, BASE_TOOL_SCHEMAS, COMPLETE_TASK_TOOL, build_db_tools
from .db import TaskDB

logger = logging.getLogger(__name__)

MAX_DELEGATION_DEPTH = 3
MAX_ITERATIONS = 60
PRINT_PREVIEW_CHARS = 800  # keep the live console readable; full content still goes to the transcript file

# Context-budget management for small local models. Ollama truncates from the
# FRONT of the token sequence once num_ctx is exceeded, which can silently drop
# the system prompt/persona after enough tool-call turns. We proactively collapse
# older turns into a one-line-per-action summary well before that happens.
# Also: some Ollama/llama.cpp backends get genuinely unstable (KV-cache
# checkpoint churn, occasional 500s) as a conversation approaches tens of
# thousands of real tokens, even well under num_ctx — compact earlier rather
# than riding the edge.
COMPACTION_RATIO = float(os.getenv("LLM_COMPACTION_RATIO", "0.5"))  # start compacting once history exceeds this fraction of num_ctx
KEEP_RECENT_MESSAGES = 6  # always keep the last N messages verbatim for continuity
CHARS_PER_TOKEN = 4  # rough estimate, no tokenizer dependency needed

# Small models sometimes retry the exact same failing tool call over and over
# with zero adaptation (observed: 17x identical broken decrypt() call in a row).
# Nothing in a plain "call tool, feed back result" loop tells the model it's
# already tried this — so we track it ourselves.
REPEAT_WARN_THRESHOLD = 2  # inject a warning starting on the 2nd identical repeat (3rd call)
REPEAT_ABORT_THRESHOLD = 4  # give up on the task starting on the 4th identical repeat (5th call)

# Small models also get "lost" and keep enumerating (different flags/targets/
# ports each time, so exact-match repeat detection above never triggers) well
# past the point of having enough to act on. Throttle by broad *category* of
# command, not exact args.
ENUMERATION_COMMAND_PATTERN = re.compile(
    r"\bnmap\b|\bgobuster\b|\bffuf\b|\bferoxbuster\b|\bdirsearch\b|\bnikto\b|"
    r"\bwhatweb\b|\bhttpx\b|\bnuclei\b|\bdnsx\b|\bsubfinder\b|\bwpscan\b|\bnetexec\b|\bnxc\b",
    re.IGNORECASE,
)
ENUMERATION_WARN_THRESHOLD = 6  # nudge to check findings/facts after this many scan-type calls
ENUMERATION_HARD_STOP = 12  # force-complete the task after this many, using whatever was found

# Reorient every N iterations: re-state the objective + known facts/findings so
# the model doesn't drift as the conversation (even compacted) grows long.
REORIENT_INTERVAL = 8


class AgentRunner:
    def __init__(
        self,
        agent_name: str,
        workspace_dir: Path,
        agents_dir: Path,
        llm_config: LlmConfig | None = None,
        depth: int = 0,
        max_iterations: int = MAX_ITERATIONS,
        db: TaskDB | None = None,
        task_id: int | None = None,
    ) -> None:
        self.agent_name = agent_name
        self.workspace_dir = workspace_dir
        self.agents_dir = agents_dir
        self.llm = LlmClient(llm_config)
        self.loader = AgentLoader(agents_dir)
        self.depth = depth
        self.max_iterations = max_iterations
        self.db = db
        self.task_id = task_id

    def _tools(self) -> tuple[list[dict], dict]:
        schemas = list(BASE_TOOL_SCHEMAS)
        impls = dict(BASE_TOOL_IMPLS)

        if self.db is not None:
            db_schemas, db_impls = build_db_tools(self.db, self.agent_name, self.task_id)
            schemas += db_schemas
            impls.update(db_impls)

        if self.depth < MAX_DELEGATION_DEPTH:
            schemas.append({
                "type": "function",
                "function": {
                    "name": "delegate_agent",
                    "description": (
                        "Hand off a task to a specialist agent (e.g. ReconAgent, "
                        "WebTestAgent, ExploitAgent, PrivEscAgent, FlagAgent, "
                        "LoggerAgent). Runs that agent's full tool-calling loop to "
                        "completion and returns its final report as text."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "agent": {"type": "string", "enum": AGENT_NAMES},
                            "task": {
                                "type": "string",
                                "description": "The task/context to hand to that agent, including any relevant loot already gathered.",
                            },
                        },
                        "required": ["agent", "task"],
                    },
                },
            })
            impls["delegate_agent"] = self._delegate_agent

        return schemas, impls

    def _delegate_agent(self, agent: str, task: str) -> str:
        logger.info("[%s] delegating to %s", self.agent_name, agent)
        print(f"\n[DELEGATE] {self.agent_name} -> {agent}\n")
        sub_task_id = None
        if self.db is not None:
            sub_task_id = self.db.create_task(agent=agent, title=f"delegated by {self.agent_name}", description=task, parent_id=self.task_id)
            self.db.update_task(sub_task_id, status="in_progress")
        sub_runner = AgentRunner(
            agent_name=agent,
            workspace_dir=self.workspace_dir,
            agents_dir=self.agents_dir,
            llm_config=self.llm.config,
            depth=self.depth + 1,
            max_iterations=self.max_iterations,
            db=self.db,
            task_id=sub_task_id,
        )
        return sub_runner.run(task)

    def run(self, kickoff_message: str) -> str:
        system_prompt = self.loader.system_prompt(self.agent_name, db_enabled=self.db is not None)
        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": kickoff_message},
        ]
        tool_schemas, tool_impls = self._tools()
        transcript_path = self._open_transcript()
        print(f"[{self.agent_name}] transcript: {transcript_path}")
        self._log_transcript(transcript_path, messages)  # record system+user turn
        repeat_counts: dict[str, int] = {}
        enumeration_count = 0

        for iteration in range(1, self.max_iterations + 1):
            messages = self._maybe_compact(messages, transcript_path)

            if iteration > 1 and iteration % REORIENT_INTERVAL == 1:
                reorient_msg = self._build_reorientation(kickoff_message, iteration)
                messages.append(reorient_msg)
                self._log_transcript(transcript_path, [reorient_msg])
                print(f"[{self.agent_name}] iter {iteration}: reorientation reminder injected")

            try:
                response = self.llm.complete(messages, tools=tool_schemas)
            except Exception as exc:  # noqa: BLE001 - backend crashes shouldn't kill the whole engagement
                error_msg = f"[{self.agent_name}] LLM call failed after retries: {exc}"
                print(error_msg)
                logger.error(error_msg)
                self._log_transcript(transcript_path, [{"role": "system", "content": f"[LLM ERROR] {exc}"}])
                if self.db is not None and self.task_id is not None:
                    self.db.update_task(self.task_id, status="failed", result=error_msg)
                return error_msg
            message = response.choices[0].message
            tool_calls = getattr(message, "tool_calls", None) or []

            assistant_msg: dict = {"role": "assistant", "content": message.content or ""}
            if tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ]
            messages.append(assistant_msg)
            self._log_transcript(transcript_path, [assistant_msg])

            # Print the model's own reasoning/plan text, not just the tool calls it
            # emits alongside it — this is the "what is it doing" visibility gap.
            if message.content:
                print(f"\n[{self.agent_name}] iter {iteration} says:\n{self._preview(message.content)}\n")

            if not tool_calls:
                # Model produced a plain-text response with no further tool calls —
                # treat it as this agent's final report and end the loop.
                if not message.content:
                    print(f"[{self.agent_name}] WARNING: model returned an empty final message with no tool calls")
                    if self.db is not None and self.task_id is not None:
                        self.db.update_task(self.task_id, status="failed", result="model went quiet with no tool calls and no final text")
                elif self.db is not None and self.task_id is not None:
                    # Model never called complete_task explicitly but did give a final
                    # answer — still record it so the task isn't left dangling as pending.
                    self.db.update_task(self.task_id, status="completed", result=message.content)
                return message.content or ""

            for tc in tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}

                impl = tool_impls.get(name)
                print(f"[{self.agent_name}] iter {iteration}: {name}({args})")
                if impl is None:
                    result = f"[error: unknown tool {name!r}]"
                else:
                    try:
                        result = impl(**args)
                    except Exception as exc:  # noqa: BLE001
                        result = f"[error running tool {name}: {exc}]"

                repeat_key = f"{name}:{tc.function.arguments}"
                repeat_counts[repeat_key] = repeat_counts.get(repeat_key, 0) + 1
                repeats = repeat_counts[repeat_key]

                if repeats > REPEAT_ABORT_THRESHOLD:
                    blocked_msg = (
                        f"[{self.agent_name}] ABORTING: called the exact same {name} "
                        f"with identical arguments {repeats} times in a row without any "
                        "change in approach. This task is blocked, not making progress."
                    )
                    print(blocked_msg)
                    if self.db is not None and self.task_id is not None:
                        self.db.update_task(self.task_id, status="blocked", result=blocked_msg)
                    return blocked_msg

                if repeats > REPEAT_WARN_THRESHOLD:
                    result = (
                        f"{result}\n\n[REPEAT WARNING: you have called this exact tool with these "
                        f"exact arguments {repeats} times now and gotten the same result every time. "
                        "Repeating it again will not help. Either change your approach (different "
                        "arguments, different tool, fix the actual bug in the command) or call "
                        "complete_task with status='blocked' explaining why you're stuck."
                    )

                if name == "run_command" and ENUMERATION_COMMAND_PATTERN.search(str(args.get("command", ""))):
                    enumeration_count += 1

                    if enumeration_count >= ENUMERATION_HARD_STOP:
                        findings_summary = self._findings_summary()
                        stop_msg = (
                            f"[{self.agent_name}] AUTO-COMPLETING: ran {enumeration_count} enumeration/scan "
                            "commands in this task without finishing — that's almost certainly more than "
                            "enough. Stopping here rather than continuing to enumerate.\n\n"
                            f"Findings recorded so far:\n{findings_summary}"
                        )
                        print(stop_msg)
                        if self.db is not None and self.task_id is not None:
                            self.db.update_task(self.task_id, status="completed", result=stop_msg)
                        return stop_msg

                    if enumeration_count == ENUMERATION_WARN_THRESHOLD:
                        result = (
                            f"{result}\n\n[ENUMERATION CHECKPOINT: you've now run {enumeration_count} "
                            "scan/enumeration commands in this task. Call list_findings and get_facts "
                            "before running more — you likely already have enough to act on or hand off "
                            "via create_subtask/complete_task. Only keep enumerating if you have a specific "
                            "unanswered question a new scan would resolve."
                        )

                print(f"[{self.agent_name}]   -> {self._preview(str(result))}")

                tool_msg = {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": name,
                    "content": str(result),
                }
                messages.append(tool_msg)
                self._log_transcript(transcript_path, [tool_msg])

                if name == COMPLETE_TASK_TOOL:
                    # Explicit, deterministic termination — don't wait for the model
                    # to go quiet on its own, which small models sometimes never do.
                    return str(result)

        logger.warning("[%s] hit max_iterations (%d) without a final answer", self.agent_name, self.max_iterations)
        if self.db is not None and self.task_id is not None:
            self.db.update_task(self.task_id, status="failed", result=f"hit max_iterations ({self.max_iterations}) without calling complete_task")
        return f"[{self.agent_name} stopped after {self.max_iterations} iterations without a final answer]"

    def _open_transcript(self) -> Path:
        log_dir = self.workspace_dir / "loot" / "agent_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%S")
        return log_dir / f"{stamp}-{self.agent_name}-d{self.depth}-{uuid.uuid4().hex[:8]}.jsonl"

    @staticmethod
    def _log_transcript(path: Path, messages: list[dict]) -> None:
        with path.open("a") as fh:
            for msg in messages:
                fh.write(json.dumps(msg) + "\n")

    @staticmethod
    def _preview(text: str) -> str:
        if len(text) <= PRINT_PREVIEW_CHARS:
            return text
        return text[:PRINT_PREVIEW_CHARS] + f"\n...[{len(text) - PRINT_PREVIEW_CHARS} more chars — see transcript file]"

    def _findings_summary(self) -> str:
        if self.db is None:
            return "[no task DB attached]"
        findings = self.db.list_findings()
        if not findings:
            return "[none recorded]"
        return "\n".join(f"- [{f['category']}] {f['summary']}" for f in findings)

    def _build_reorientation(self, kickoff_message: str, iteration: int) -> dict:
        """
        Periodic "what am I even doing" reminder. Small models drift as a
        conversation grows — even compacted history loses salience on the
        original objective after enough turns of tool-call noise.
        """
        facts = self.db.get_facts() if self.db is not None else {}
        facts_str = "\n".join(f"{k}: {v}" for k, v in facts.items()) or "[none]"
        content = (
            f"## Reorientation check (iteration {iteration}/{self.max_iterations})\n\n"
            "You may be several tool calls deep and losing track. Re-read your original "
            f"objective below before continuing:\n\n{kickoff_message}\n\n"
            f"Known facts:\n{facts_str}\n\n"
            f"Findings recorded so far:\n{self._findings_summary()}\n\n"
            "If the above is already enough to satisfy your objective, call complete_task "
            "now instead of continuing to gather more. Do not re-run enumeration you've "
            "already done — check list_findings/get_facts first."
        )
        return {"role": "system", "content": content}

    @staticmethod
    def _estimate_tokens(messages: list[dict]) -> int:
        total = 0
        for m in messages:
            total += len(m.get("content") or "") // CHARS_PER_TOKEN
            for tc in m.get("tool_calls") or []:
                total += len(json.dumps(tc)) // CHARS_PER_TOKEN
            total += 8  # per-message role/framing overhead
        return total

    def _maybe_compact(self, messages: list[dict], transcript_path: Path) -> list[dict]:
        """
        Collapse older tool-call/result turns into a single one-line-per-action
        summary once the running history crosses COMPACTION_RATIO of num_ctx.
        Always keeps: the system prompt, the original kickoff message, and the
        last KEEP_RECENT_MESSAGES verbatim for continuity.
        """
        budget = int(self.llm.config.context_window * COMPACTION_RATIO)
        if self._estimate_tokens(messages) <= budget:
            return messages
        if len(messages) <= 2 + KEEP_RECENT_MESSAGES:
            return messages  # nothing meaningful to compact yet

        system_msg, kickoff_msg = messages[0], messages[1]
        head = messages[2:-KEEP_RECENT_MESSAGES]
        tail = messages[-KEEP_RECENT_MESSAGES:]
        if not head:
            return messages

        lines: list[str] = []
        for m in head:
            role = m.get("role")
            if role == "assistant" and m.get("tool_calls"):
                for tc in m["tool_calls"]:
                    fn = tc["function"]
                    lines.append(f"- called {fn['name']}({fn['arguments']})")
            elif role == "assistant" and m.get("content"):
                lines.append(f"- reasoned: {m['content'][:200]}")
            elif role == "tool":
                preview = (m.get("content") or "").replace("\n", " ")[:200]
                lines.append(f"  -> {preview}")

        summary_msg = {
            "role": "system",
            "content": (
                "## Progress so far (older turns compacted to stay within context budget)\n"
                + "\n".join(lines)
            ),
        }
        compacted = [system_msg, kickoff_msg, summary_msg] + tail
        logger.info(
            "[%s] compacted %d messages -> %d (~%d tokens -> ~%d)",
            self.agent_name, len(messages), len(compacted),
            self._estimate_tokens(messages), self._estimate_tokens(compacted),
        )
        print(f"[{self.agent_name}] context compacted: {len(messages)} -> {len(compacted)} messages")
        self._log_transcript(transcript_path, [{"role": "system", "content": "[COMPACTION EVENT]"}, summary_msg])
        return compacted
