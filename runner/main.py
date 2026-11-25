#!/usr/bin/env python3
"""
Standalone CTF agent runner — litellm/Ollama replacement for the
`gh copilot` + @AgentName chat workflow, for when you want to drive the
agents/ definitions against a local model instead.

Usage (matches the run-ctf.sh container layout: /workspace is the mounted
project dir, /workspace/agents is the read-only agent-definitions mount):

    python3 -m runner.main
    python3 -m runner.main --agent OrchestratorAgent --model qwen2.5:14b
    OLLAMA_API_BASE=http://host.docker.internal:11434 python3 -m runner.main

Reads /workspace/ctf-context.yaml the same way the OrchestratorAgent
definition describes, and assembles a kickoff message equivalent to
prompts/ctf-htb-kickoff.prompt.md.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import yaml

from .agent_runner import AgentRunner
from .db import TaskDB
from .llm import LlmConfig

DEFAULT_KICKOFF_TEMPLATE = """\
Start CTF engagement.

Inputs:
  CTF context: {context_path}

Execution policy:
  - Use agents/OrchestratorAgent/definition.md as the workflow source of truth.
  - Use agents/shared/constraints.md and agents/shared/output-schemas.md.
  - All output goes to {workspace}/loot/.
  - Connect VPN automatically before any scanning if not already connected.
  - Follow the attack flow: Recon -> Exploit -> Foothold -> PrivEsc -> Flags.
  - Capture user.txt and root.txt to loot/flags.yaml.
  - Every confirmed exploit, credential, hash crack, or flag MUST be logged via
    LoggerAgent to loot/exploit_log.yaml.
  - Never expand scope beyond the single target IP in ctf-context.yaml.

Begin.
"""


def build_kickoff_message(workspace: Path, context_path: Path) -> str:
    msg = DEFAULT_KICKOFF_TEMPLATE.format(context_path=context_path, workspace=workspace)
    if context_path.exists():
        try:
            ctx = yaml.safe_load(context_path.read_text()) or {}
            msg += f"\n\nctf-context.yaml contents:\n```yaml\n{yaml.dump(ctx)}```\n"
        except Exception as exc:  # noqa: BLE001
            msg += f"\n\n[warning: failed to parse {context_path}: {exc}]\n"
    else:
        msg += f"\n\n[warning: {context_path} does not exist yet — create it before scanning, or ask the operator for target details.]\n"
    return msg


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"), help="Workspace root (default: /workspace)")
    parser.add_argument("--agents-dir", type=Path, default=None, help="Override agents/ directory (default: <workspace>/agents)")
    parser.add_argument("--context", type=Path, default=None, help="Override ctf-context.yaml path")
    parser.add_argument("--agent", default="OrchestratorAgent", help="Agent to run (default: OrchestratorAgent)")
    parser.add_argument("--model", default=None, help="Ollama model name (default: $LLM_MODEL or qwen2.5:14b)")
    parser.add_argument("--api-base", default=None, help="Ollama API base (default: $OLLAMA_API_BASE or http://localhost:11434)")
    parser.add_argument("--max-iterations", type=int, default=60)
    parser.add_argument("--task", default=None, help="Freeform task instead of the default OrchestratorAgent kickoff message")
    parser.add_argument("--no-db", action="store_true", help="Disable the SQLite task/fact store (get_facts/set_fact/create_subtask/complete_task tools)")
    parser.add_argument("--fresh-db", action="store_true", help="Wipe loot/agent_tasks.db before starting (default: reopen/reuse it, so facts/tasks from a prior run in this same workspace persist)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")

    workspace = args.workspace.resolve()
    agents_dir = (args.agents_dir or workspace / "agents").resolve()
    context_path = (args.context or workspace / "ctf-context.yaml").resolve()

    llm_config = LlmConfig()
    if args.model:
        llm_config.model = args.model
    if args.api_base:
        llm_config.api_base = args.api_base

    print(f"[+] Agent:     {args.agent}")
    print(f"[+] Model:     ollama_chat/{llm_config.model} @ {llm_config.api_base}")
    print(f"[+] Workspace: {workspace}")
    print(f"[+] Agents:    {agents_dir}")
    print()

    kickoff = args.task or build_kickoff_message(workspace, context_path)

    db = None
    task_id = None
    if not args.no_db:
        db_path = workspace / "loot" / "agent_tasks.db"
        if args.fresh_db and db_path.exists():
            db_path.unlink()
            print(f"[+] Task DB:   wiped {db_path} (--fresh-db)")
        elif db_path.exists():
            print(f"[!] Task DB:   reusing existing {db_path} — facts/tasks from a prior run here will still be visible via get_facts. Pass --fresh-db to start clean.")
        db = TaskDB(db_path)
        task_id = db.create_task(agent=args.agent, title="top-level invocation", description=kickoff)
        db.update_task(task_id, status="in_progress")
        print(f"[+] Task DB:   {db_path} (task #{task_id})")

    runner = AgentRunner(
        agent_name=args.agent,
        workspace_dir=workspace,
        agents_dir=agents_dir,
        llm_config=llm_config,
        max_iterations=args.max_iterations,
        db=db,
        task_id=task_id,
    )

    result = runner.run(kickoff)

    print("\n" + "=" * 80)
    print(f"[{args.agent} final report]")
    print("=" * 80)
    print(result)


if __name__ == "__main__":
    main()
