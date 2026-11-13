"""Application metadata database (threads index, execution log, quizzes).

Conversation CONTENT is not stored here - it lives in the LangGraph checkpointer. This DB only keeps what
LangGraph does not: the per-user thread list/titles, a log of graph executions, and quiz history.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.errors import NotFoundError

DEFAULT_TITLE = "New conversation"

SCHEMA = """
CREATE TABLE IF NOT EXISTS threads (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'chat',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_threads_user ON threads(user_id, kind, updated_at);
CREATE TABLE IF NOT EXISTS executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT UNIQUE NOT NULL, thread_id TEXT NOT NULL,
    user_id TEXT NOT NULL, kind TEXT NOT NULL, created_at TEXT NOT NULL, intent TEXT, status TEXT NOT NULL,
    duration_ms INTEGER, record TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_exec_thread ON executions(thread_id, id);
CREATE INDEX IF NOT EXISTS idx_exec_user ON executions(user_id, id);
CREATE TABLE IF NOT EXISTS quizzes (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, topic TEXT NOT NULL, difficulty TEXT NOT NULL,
    questions TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS quiz_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, quiz_id TEXT NOT NULL, user_id TEXT NOT NULL,
    score INTEGER NOT NULL, total INTEGER NOT NULL, answers TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attempts_user ON quiz_attempts(user_id, id);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AppDB:
    def __init__(self, path: Path):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.RLock()
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def _all(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    # ---------------------------------------------------------------- threads
    def create_thread(self, thread_id: str, user_id: str, title: str | None, kind: str = "chat") -> dict[str, Any]:
        ts = now()
        self._exec("INSERT INTO threads VALUES (?,?,?,?,?,?)", (thread_id, user_id, title or DEFAULT_TITLE, kind, ts, ts))
        return self.get_thread(user_id, thread_id)

    def get_thread(self, user_id: str, thread_id: str) -> dict[str, Any]:
        rows = self._all("SELECT * FROM threads WHERE id=? AND user_id=?", (thread_id, user_id))
        if not rows:
            raise NotFoundError(f"Conversation '{thread_id}' not found.")
        return dict(rows[0])

    def list_threads(self, user_id: str, kind: str = "chat") -> list[dict[str, Any]]:
        return [dict(r) for r in self._all(
            "SELECT * FROM threads WHERE user_id=? AND kind=? ORDER BY updated_at DESC, created_at DESC", (user_id, kind))]

    def rename_thread(self, user_id: str, thread_id: str, title: str) -> dict[str, Any]:
        self.get_thread(user_id, thread_id)
        self._exec("UPDATE threads SET title=?, updated_at=? WHERE id=?", (title, now(), thread_id))
        return self.get_thread(user_id, thread_id)

    def touch_thread(self, thread_id: str, title: str | None = None) -> None:
        if title:
            self._exec("UPDATE threads SET title=?, updated_at=? WHERE id=?", (title, now(), thread_id))
        else:
            self._exec("UPDATE threads SET updated_at=? WHERE id=?", (now(), thread_id))

    def delete_thread(self, user_id: str, thread_id: str) -> None:
        self.get_thread(user_id, thread_id)
        self._exec("DELETE FROM threads WHERE id=?", (thread_id,))
        self._exec("DELETE FROM executions WHERE thread_id=?", (thread_id,))

    # ------------------------------------------------------------- executions
    def save_execution(self, record: dict[str, Any], kind: str) -> None:
        self._exec(
            "INSERT OR REPLACE INTO executions (request_id, thread_id, user_id, kind, created_at, intent, status, duration_ms, record) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (record["request_id"], record["thread_id"], record["user_id"], kind, record["created_at"],
             record.get("intent"), record["status"], record.get("duration_ms"), json.dumps(record)),
        )

    def latest_execution(self, user_id: str, thread_id: str | None = None, kind: str | None = None) -> dict[str, Any] | None:
        sql, params = "SELECT record FROM executions WHERE user_id=?", [user_id]
        if thread_id:
            sql += " AND thread_id=?"
            params.append(thread_id)
        if kind:
            sql += " AND kind=?"
            params.append(kind)
        rows = self._all(sql + " ORDER BY id DESC LIMIT 1", tuple(params))
        return json.loads(rows[0]["record"]) if rows else None

    def recent_executions(self, user_id: str, limit: int = 10) -> list[dict[str, Any]]:
        rows = self._all("SELECT record FROM executions WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit))
        return [json.loads(r["record"]) for r in rows]

    def execution_stats(self, user_id: str) -> dict[str, Any]:
        rows = self._all("SELECT intent, COUNT(*) AS n FROM executions WHERE user_id=? AND status='ok' GROUP BY intent", (user_id,))
        return {r["intent"] or "unknown": r["n"] for r in rows}

    # ---------------------------------------------------------------- quizzes
    def save_quiz(self, quiz_id: str, user_id: str, topic: str, difficulty: str, questions: list[dict[str, Any]]) -> None:
        self._exec("INSERT INTO quizzes VALUES (?,?,?,?,?,?)", (quiz_id, user_id, topic, difficulty, json.dumps(questions), now()))

    def get_quiz(self, user_id: str, quiz_id: str) -> dict[str, Any]:
        rows = self._all("SELECT * FROM quizzes WHERE id=? AND user_id=?", (quiz_id, user_id))
        if not rows:
            raise NotFoundError(f"Quiz '{quiz_id}' not found.")
        d = dict(rows[0])
        d["questions"] = json.loads(d["questions"])
        return d

    def list_quizzes(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        out = []
        for r in self._all("SELECT * FROM quizzes WHERE user_id=? ORDER BY created_at DESC, rowid DESC LIMIT ?", (user_id, limit)):
            best = self._all("SELECT MAX(score) AS s, COUNT(*) AS n FROM quiz_attempts WHERE quiz_id=?", (r["id"],))[0]
            out.append({"id": r["id"], "topic": r["topic"], "difficulty": r["difficulty"], "created_at": r["created_at"],
                        "num_questions": len(json.loads(r["questions"])), "attempts": best["n"], "best_score": best["s"]})
        return out

    def save_attempt(self, quiz_id: str, user_id: str, score: int, total: int, answers: list[Any]) -> None:
        self._exec("INSERT INTO quiz_attempts (quiz_id,user_id,score,total,answers,created_at) VALUES (?,?,?,?,?,?)",
                   (quiz_id, user_id, score, total, json.dumps(answers), now()))

    def quiz_activity(self, user_id: str) -> dict[str, Any]:
        gen = self._all("SELECT COUNT(*) AS n FROM quizzes WHERE user_id=?", (user_id,))[0]["n"]
        att = self._all("SELECT COUNT(*) AS n, SUM(score) AS s, SUM(total) AS t FROM quiz_attempts WHERE user_id=?", (user_id,))[0]
        recent = [dict(r) for r in self._all(
            "SELECT a.id, a.score, a.total, a.created_at, q.topic FROM quiz_attempts a JOIN quizzes q ON q.id=a.quiz_id "
            "WHERE a.user_id=? ORDER BY a.id DESC LIMIT 5", (user_id,))]
        return {
            "quizzes_generated": gen,
            "attempts": att["n"],
            "average_percent": round(100 * att["s"] / att["t"]) if att["t"] else None,
            "recent_attempts": recent,
        }

    def purge_user(self, user_id: str) -> list[str]:
        """Delete every row belonging to a user. Returns the thread ids that were removed."""
        ids = [r["id"] for r in self._all("SELECT id FROM threads WHERE user_id=?", (user_id,))]
        for table in ("executions", "quiz_attempts", "quizzes", "threads"):
            self._exec(f"DELETE FROM {table} WHERE user_id=?", (user_id,))
        return ids
