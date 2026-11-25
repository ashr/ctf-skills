"""
SQLite-backed task/fact/event store shared by the Orchestrator and every
worker AgentRunner. Exists to solve two problems for small local models:

  1. "Done" needs to be an explicit signal, not inferred from the model
     going quiet (see complete_task in tools.py) — small models sometimes
     just stop producing tool calls without actually finishing.
  2. Context shouldn't grow with total conversation history. Facts learned
     by one task (target IP, open ports, discovered creds) are written once
     and any other task/agent reads them back via get_facts() instead of
     needing the full transcript that discovered them.

One file per workspace: <workspace>/loot/agent_tasks.db.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id INTEGER,
    agent TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | in_progress | completed | blocked | failed
    result TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS facts (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    set_by TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER,
    agent TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- Running evidence log, distinct from `facts` (single current value per key).
-- Agents record_finding() as they discover things and list_findings() before
-- enumerating further, so "have I already found this?" has an actual answer
-- instead of needing to re-read/re-derive it from a huge transcript.
CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER,
    agent TEXT NOT NULL,
    category TEXT NOT NULL,  -- port | endpoint | vuln | credential | note
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class TaskDB:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: sub-agents may run on the same connection
        # from nested calls within one process; there's no real concurrency here.
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    @staticmethod
    def _now() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # ── tasks ────────────────────────────────────────────────────────────

    def create_task(self, agent: str, title: str, description: str, parent_id: int | None = None) -> int:
        now = self._now()
        cur = self.conn.execute(
            "INSERT INTO tasks (parent_id, agent, title, description, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'pending', ?, ?)",
            (parent_id, agent, title, description, now, now),
        )
        self.conn.commit()
        task_id = cur.lastrowid
        self.log_event(task_id, "system", f"task created for {agent}: {title}")
        return task_id

    def get_task(self, task_id: int) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None

    def list_tasks(self, status: str | None = None) -> list[dict[str, Any]]:
        if status:
            rows = self.conn.execute("SELECT * FROM tasks WHERE status = ? ORDER BY id", (status,)).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM tasks ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def get_next_pending(self) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM tasks WHERE status = 'pending' ORDER BY id LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def update_task(self, task_id: int, status: str, result: str | None = None) -> None:
        self.conn.execute(
            "UPDATE tasks SET status = ?, result = COALESCE(?, result), updated_at = ? WHERE id = ?",
            (status, result, self._now(), task_id),
        )
        self.conn.commit()
        self.log_event(task_id, "system", f"task -> {status}" + (f": {result[:200]}" if result else ""))

    # ── facts ────────────────────────────────────────────────────────────

    def set_fact(self, key: str, value: Any, set_by: str) -> None:
        serialized = value if isinstance(value, str) else json.dumps(value)
        self.conn.execute(
            "INSERT INTO facts (key, value, set_by, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, set_by = excluded.set_by, updated_at = excluded.updated_at",
            (key, serialized, set_by, self._now()),
        )
        self.conn.commit()

    def get_facts(self, keys: list[str] | None = None) -> dict[str, str]:
        if keys:
            placeholders = ",".join("?" for _ in keys)
            rows = self.conn.execute(f"SELECT key, value FROM facts WHERE key IN ({placeholders})", keys).fetchall()
        else:
            rows = self.conn.execute("SELECT key, value FROM facts").fetchall()
        return {r["key"]: r["value"] for r in rows}

    # ── events ───────────────────────────────────────────────────────────

    def log_event(self, task_id: int | None, agent: str, message: str) -> None:
        self.conn.execute(
            "INSERT INTO events (task_id, agent, message, created_at) VALUES (?, ?, ?, ?)",
            (task_id, agent, message, self._now()),
        )
        self.conn.commit()

    def get_events(self, task_id: int | None = None) -> list[dict[str, Any]]:
        if task_id is not None:
            rows = self.conn.execute("SELECT * FROM events WHERE task_id = ? ORDER BY id", (task_id,)).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM events ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    # ── findings ─────────────────────────────────────────────────────────

    def record_finding(self, agent: str, category: str, summary: str, task_id: int | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO findings (task_id, agent, category, summary, created_at) VALUES (?, ?, ?, ?, ?)",
            (task_id, agent, category, summary, self._now()),
        )
        self.conn.commit()
        return cur.lastrowid

    def list_findings(self, category: str | None = None) -> list[dict[str, Any]]:
        if category:
            rows = self.conn.execute(
                "SELECT * FROM findings WHERE category = ? ORDER BY id", (category,)
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM findings ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def count_findings(self) -> int:
        return self.conn.execute("SELECT COUNT(*) AS c FROM findings").fetchone()["c"]

    def close(self) -> None:
        self.conn.close()
