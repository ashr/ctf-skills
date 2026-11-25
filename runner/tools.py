"""
Tool implementations available to every CTF agent loop.

Kept intentionally small: a shell escape hatch (everything in
agents/shared/tooling.md is a CLI binary, so `run_command` covers virtually
all agent needs) plus basic file I/O for reading/writing loot files. Agent
delegation (`delegate_agent`) is wired up in agent_runner.py since it needs a
reference back to the runner for recursion.

build_db_tools() adds task-queue/shared-fact tools when a TaskDB is attached
to the run — see runner/db.py for why (explicit completion signal + shared
facts instead of re-stating context in every prompt).
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .db import TaskDB

MAX_OUTPUT_CHARS = 12_000  # keep tool results from blowing up the local model's context window
DEFAULT_TIMEOUT = 600  # full-port nmap/gobuster/etc. routinely exceed 120s

# Tools/flags that routinely run well past DEFAULT_TIMEOUT (full-port scans,
# large-wordlist brute force, NSE script scans). Applied only when the model
# doesn't pass its own timeout — small models often forget to raise it for
# these, and the old 120s default left orphaned nmap processes racing every
# retry (see docs). --script=vuln/-sU/-A are NSE/UDP/aggressive scans that are
# just as slow as -p- but don't match the -p-/--top-ports patterns alone.
HEAVY_COMMAND_PATTERN = re.compile(
    r"-p-|--top-ports\s+\d{3,}|--script(=|\s)|(?<!\S)-sU(?!\S)|(?<!\S)-A(?!\S)|"
    r"\bgobuster\b|\bffuf\b|\bferoxbuster\b|\bdirsearch\b|"
    r"\bhydra\b|\bmedusa\b|\bwpscan\b|\bnikto\b|\bnuclei\b|\bmasscan\b|\bsqlmap\b",
    re.IGNORECASE,
)
HEAVY_COMMAND_TIMEOUT = 1800  # 30 min


def _decode(data) -> str:
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode(errors="replace")
    return data


def run_command(command: str, timeout: int | None = None, cwd: str | None = None) -> str:
    """
    Run a shell command and return combined stdout+stderr, truncated.

    Uses its own process group (start_new_session=True) so that on timeout we
    can kill the whole tree — with plain shell=True + timeout, only the /bin/sh
    wrapper gets killed and long-running children (nmap, gobuster, ...) are
    left running orphaned in the background, silently racing future calls.
    """
    if timeout is None:
        timeout = HEAVY_COMMAND_TIMEOUT if HEAVY_COMMAND_PATTERN.search(command) else DEFAULT_TIMEOUT
    proc = subprocess.Popen(
        command,
        shell=True,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        header = f"[exit_code={proc.returncode}]\n"
        output = _decode(stdout) + _decode(stderr)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
        stdout, stderr = proc.communicate()  # reap + collect whatever was buffered
        header = f"[timed out after {timeout}s — process group killed]\n"
        output = _decode(stdout) + _decode(stderr)
    except Exception as exc:  # noqa: BLE001 - surface any failure back to the model
        return f"[error running command: {exc}]"

    return _truncate(header + output)


def read_file(path: str, max_bytes: int = MAX_OUTPUT_CHARS) -> str:
    try:
        data = Path(path).read_text(errors="replace")
    except Exception as exc:  # noqa: BLE001
        return f"[error reading {path}: {exc}]"
    return _truncate(data, max_bytes)


def write_file(path: str, content: str, append: bool = False) -> str:
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with p.open(mode) as fh:
            fh.write(content)
        return f"[wrote {len(content)} bytes to {path}{' (appended)' if append else ''}]"
    except Exception as exc:  # noqa: BLE001
        return f"[error writing {path}: {exc}]"


def list_dir(path: str) -> str:
    try:
        entries = sorted(Path(path).iterdir())
    except Exception as exc:  # noqa: BLE001
        return f"[error listing {path}: {exc}]"
    lines = [f"{'d' if e.is_dir() else 'f'}  {e.name}" for e in entries]
    return _truncate("\n".join(lines) or "[empty]")


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated, {len(text) - limit} more chars]"


# OpenAI-style tool schemas (litellm/ollama_chat native tool-calling format)
BASE_TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": (
                "Run a shell command in the CTF container (nmap, curl, sqlmap, hydra, "
                "impacket scripts, etc. — see agents/shared/tooling.md for the full "
                "tool inventory). Returns combined stdout+stderr and the exit code. "
                "On timeout the entire process tree is killed (no orphaned scans keep "
                "running in the background). Known slow tools (full-port nmap, gobuster, "
                "ffuf, hydra, nuclei, sqlmap, ...) already get a longer default timeout "
                "automatically — pass an explicit timeout to override it further."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute."},
                    "timeout": {"type": "integer", "description": "Timeout in seconds. Default: 600, or 1800 for known slow scan tools."},
                    "cwd": {"type": "string", "description": "Working directory (default /workspace)."},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a text file (e.g. a loot/*.yaml file or scan output).",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write (or append to) a text file, e.g. loot/recon_results.yaml.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "append": {"type": "boolean", "description": "Append instead of overwrite (default false)."},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List the contents of a directory.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
]

BASE_TOOL_IMPLS = {
    "run_command": run_command,
    "read_file": read_file,
    "write_file": write_file,
    "list_dir": list_dir,
}

# Name of the tool AgentRunner treats as an explicit, unambiguous "I'm done"
# signal instead of inferring completion from the model going quiet.
COMPLETE_TASK_TOOL = "complete_task"


def build_db_tools(db: "TaskDB", agent_name: str, task_id: int | None) -> tuple[list[dict], dict]:
    """
    Tools available when a TaskDB is attached to this run: shared facts
    (avoid re-deriving/re-stating context other tasks already learned),
    subtask creation (queue work for another agent instead of running it
    inline), and complete_task — the explicit termination signal.
    """

    def get_facts(keys: list[str] | None = None) -> str:
        facts = db.get_facts(keys)
        return "\n".join(f"{k}: {v}" for k, v in facts.items()) or "[no facts set yet]"

    def set_fact(key: str, value: str) -> str:
        db.set_fact(key, value, set_by=agent_name)
        return f"[fact set: {key} = {value}]"

    def create_subtask(agent: str, title: str, description: str) -> str:
        new_id = db.create_task(agent=agent, title=title, description=description, parent_id=task_id)
        return f"[queued task #{new_id} for {agent}: {title}]"

    def record_finding(category: str, summary: str) -> str:
        db.record_finding(agent=agent_name, category=category, summary=summary, task_id=task_id)
        return f"[finding recorded: {category}: {summary}]"

    def list_findings(category: str | None = None) -> str:
        findings = db.list_findings(category)
        if not findings:
            return "[no findings recorded yet — nothing has been confirmed this engagement]"
        return "\n".join(f"#{f['id']} [{f['category']}] ({f['agent']}) {f['summary']}" for f in findings)

    def complete_task(summary: str, status: str = "completed") -> str:
        if task_id is not None:
            db.update_task(task_id, status=status, result=summary)
        return summary

    schemas = [
        {
            "type": "function",
            "function": {
                "name": "get_facts",
                "description": (
                    "Read shared facts other tasks/agents already learned this engagement "
                    "(e.g. target_ip, open_ports, foothold_user) instead of re-deriving them."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keys": {"type": "array", "items": {"type": "string"}, "description": "Omit to get all known facts."},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "set_fact",
                "description": "Record a fact for other tasks/agents to reuse (e.g. set_fact('open_ports', '22,80,443')).",
                "parameters": {
                    "type": "object",
                    "properties": {"key": {"type": "string"}, "value": {"type": "string"}},
                    "required": ["key", "value"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_subtask",
                "description": "Queue a small, single-purpose task for another agent to pick up (does not run it inline).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent": {"type": "string"},
                        "title": {"type": "string"},
                        "description": {"type": "string", "description": "Everything that agent needs to know to do this ONE task."},
                    },
                    "required": ["agent", "title", "description"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "record_finding",
                "description": (
                    "Log a CONFIRMED discovery (something you actually saw in real tool output — "
                    "an open port, a working endpoint, a vulnerability, a credential — never something "
                    "you're guessing at). Other tasks/agents check list_findings before re-enumerating, "
                    "so recording things here is how you stop the whole engagement from repeating work."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string", "description": "e.g. port, endpoint, vuln, credential, note"},
                        "summary": {"type": "string", "description": "One confirmed fact, concrete enough to act on (e.g. 'port 4444 = ssl/ldap, anonymous bind OK')."},
                    },
                    "required": ["category", "summary"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_findings",
                "description": (
                    "List everything already confirmed and recorded this engagement. "
                    "ALWAYS call this before running another round of enumeration/scanning — "
                    "you may already have enough to act on."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"category": {"type": "string", "description": "Optional filter, e.g. 'port'."}},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": COMPLETE_TASK_TOOL,
                "description": (
                    "Call this when — and only when — your current task is finished, blocked, "
                    "or failed. This is the explicit signal that ends your turn; do not just "
                    "stop calling tools and go quiet."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string", "description": "What you did/found, or why you're blocked."},
                        "status": {"type": "string", "enum": ["completed", "blocked", "failed"]},
                    },
                    "required": ["summary"],
                },
            },
        },
    ]
    impls = {
        "get_facts": get_facts,
        "set_fact": set_fact,
        "create_subtask": create_subtask,
        "record_finding": record_finding,
        "list_findings": list_findings,
        COMPLETE_TASK_TOOL: complete_task,
    }
    return schemas, impls
