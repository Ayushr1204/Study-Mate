"""Runtime container: owns every long-lived resource (SQLite connections, graph, LLM provider)."""

from __future__ import annotations

import sqlite3
import threading
from collections import defaultdict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.store.sqlite import SqliteStore

from app.core.config import Settings
from app.core.tokens import TokenCounter
from app.graph.builder import build_graph
from app.graph.nodes import GraphDeps
from app.llm.base import LLMProvider
from app.llm.providers import build_provider
from app.memory.profile import ProfileManager
from app.services.db import AppDB


class Runtime:
    def __init__(self, settings: Settings, llm: LLMProvider | None = None):
        self.settings = settings
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.counter = TokenCounter(settings.token_counter)
        self.llm: LLMProvider = llm or build_provider(settings)

        # Short-term memory: SQLite-backed LangGraph checkpointer (one row set per thread_id).
        self._checkpoint_conn = sqlite3.connect(settings.checkpoint_db, check_same_thread=False)
        self._checkpoint_conn.execute("PRAGMA journal_mode=WAL")
        self.checkpointer = SqliteSaver(self._checkpoint_conn)

        # Long-term memory: persistent LangGraph Store (cross-thread, namespaced per user).
        self._store_conn = sqlite3.connect(settings.store_db, check_same_thread=False, isolation_level=None)
        self._store_conn.execute("PRAGMA journal_mode=WAL")
        self.store = SqliteStore(self._store_conn)
        self.store.setup()

        self.db = AppDB(settings.app_db)
        self.profiles = ProfileManager(self.store)
        self.graph = build_graph(GraphDeps(settings, self.llm, self.counter), self.checkpointer, self.store)
        self._locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
        self._locks_guard = threading.Lock()

    def thread_lock(self, thread_id: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks[thread_id]

    def close(self) -> None:
        self.db.close()
        self._checkpoint_conn.close()
        self._store_conn.close()
