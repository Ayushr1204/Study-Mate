"""Invoke the compiled graph for one request and turn the result into an execution record."""

from __future__ import annotations

import re
import time
import uuid
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage

from app.core.errors import StudyMateError
from app.core.tokens import content_to_text
from app.graph.builder import REDUCERS
from app.graph.context import role_of
from app.graph.state import utcnow
from app.runtime import Runtime
from app.services.db import DEFAULT_TITLE


def serialize_message(m: BaseMessage, index: int | None = None) -> dict[str, Any]:
    extra = dict(m.additional_kwargs or {})
    created = extra.pop("created_at", None)
    return {
        "id": m.id,
        "index": index,
        "role": role_of(m),
        "content": content_to_text(m.content),
        "created_at": created,
        "meta": extra,
    }


def thread_config(thread_id: str, user_id: str | None = None, **extra: Any) -> dict[str, Any]:
    cfg: dict[str, Any] = {"thread_id": thread_id, **extra}
    if user_id:
        cfg["user_id"] = user_id
    return {"configurable": cfg}


def get_thread_messages(rt: Runtime, thread_id: str) -> list[BaseMessage]:
    snapshot = rt.graph.get_state(thread_config(thread_id))
    return list((snapshot.values or {}).get("messages", []))


def _title_from(text: str) -> str:
    t = re.sub(r"\s+", " ", text).strip()
    return (t[:47] + "...") if len(t) > 50 else t or DEFAULT_TITLE


def _record(values: dict[str, Any], *, request_id: str, thread_id: str, user_id: str, duration_ms: int,
            status: str, error: dict[str, Any] | None, kind: str) -> dict[str, Any]:
    meta = values.get("execution_metadata") or {}
    trace = list(meta.get("trace", []))
    # Only trust a trace that belongs to THIS request (a failure before load_memory leaves an older one).
    if meta.get("run_id") != request_id:
        trace = []
    path = [t["node"] for t in trace]
    if error and error.get("node"):
        path.append(error["node"])
    gc = values.get("generated_content") or {}
    router = next((t["detail"] for t in trace if t["node"] == "router_node"), {})
    return {
        "request_id": request_id,
        "thread_id": thread_id,
        "user_id": user_id,
        "kind": kind,
        "created_at": utcnow(),
        "status": status,
        "error": error,
        "intent": values.get("intent") or router.get("intent"),
        "topic": values.get("topic") or None,
        "route": router,
        "path": path,
        "trace": trace,
        "duration_ms": duration_ms,
        "context": values.get("context_statistics") or {},
        "retrieved_memory": values.get("retrieved_memory") or {},
        "memory_changes": meta.get("memory_changes", []),
        "llm": gc.get("llm") or {},
    }


def run_graph(
    rt: Runtime,
    *,
    user_id: str,
    thread_id: str,
    text: str,
    forced_intent: str | None = None,
    payload: dict[str, Any] | None = None,
    budget: int | None = None,
    kind: str = "chat",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run the graph once. Returns (final state values, execution record). Raises StudyMateError on failure."""
    thread = rt.db.get_thread(user_id, thread_id)
    request_id = uuid.uuid4().hex
    extra: dict[str, Any] = {"request_id": request_id}  # NOT "run_id": reserved by LangGraph
    if budget:
        extra["context_budget"] = budget
    config = thread_config(thread_id, user_id, **extra)
    graph_input = {
        "messages": [HumanMessage(content=text, additional_kwargs={"created_at": utcnow()})],
        "user_id": user_id,
        "thread_id": thread_id,
        "forced_intent": forced_intent,
        "request_payload": payload or {},
    }
    with rt.thread_lock(thread_id):
        started = time.perf_counter()
        try:
            values = rt.graph.invoke(graph_input, config)
        except Exception as exc:
            duration = int((time.perf_counter() - started) * 1000)
            partial = (rt.graph.get_state(thread_config(thread_id)).values) or {}
            err = {
                "message": exc.message if isinstance(exc, StudyMateError) else f"{type(exc).__name__}: {exc}",
                "hint": getattr(exc, "hint", None),
                "code": getattr(exc, "code", "internal_error"),
                "node": getattr(exc, "studymate_node", None),
            }
            record = _record(partial, request_id=request_id, thread_id=thread_id, user_id=user_id,
                             duration_ms=duration, status="error", error=err, kind=kind)
            rt.db.save_execution(record, kind)
            rt.db.touch_thread(thread_id)
            raise
        duration = int((time.perf_counter() - started) * 1000)
        record = _record(values, request_id=request_id, thread_id=thread_id, user_id=user_id,
                         duration_ms=duration, status="ok", error=None, kind=kind)
        rt.db.save_execution(record, kind)
        new_title = _title_from(text) if kind == "chat" and thread["title"] == DEFAULT_TITLE else None
        rt.db.touch_thread(thread_id, new_title)
    return values, record


def inspect_thread_state(rt: Runtime, thread_id: str, history_limit: int = 30) -> dict[str, Any]:
    """Raw LangGraph checkpoint view of a thread (what the checkpointer actually stored)."""
    cfg = thread_config(thread_id)
    snapshot = rt.graph.get_state(cfg)
    values = snapshot.values or {}
    history = list(rt.graph.get_state_history(cfg, limit=history_limit + 1))
    checkpoints = []
    for s in history[:history_limit]:
        md = s.metadata or {}
        v = s.values or {}
        checkpoints.append({
            "checkpoint_id": s.config["configurable"]["checkpoint_id"],
            "step": md.get("step"),
            "source": md.get("source"),
            "created_at": s.created_at,
            "next": list(s.next),
            "writes": sorted((md.get("writes") or {}).keys()) if isinstance(md.get("writes"), dict) else [],
            "message_count": len(v.get("messages", [])),
            "insight_count": len(v.get("learning_insights", [])),
        })
    messages = values.get("messages", [])
    return {
        "thread_id": thread_id,
        "checkpoint_id": (snapshot.config.get("configurable") or {}).get("checkpoint_id"),
        "next": list(snapshot.next),
        "message_count": len(messages),
        "storage": {"checkpointer": type(rt.checkpointer).__name__, "database": rt.settings.checkpoint_db.name,
                    "long_term_store": type(rt.store).__name__, "store_database": rt.settings.store_db.name},
        "values": {
            "intent": values.get("intent"),
            "topic": values.get("topic"),
            "student_profile": values.get("student_profile"),
            "retrieved_memory": values.get("retrieved_memory"),
            "learning_insights": values.get("learning_insights", []),
            "context_statistics": values.get("context_statistics"),
            "execution_metadata": values.get("execution_metadata"),
            "generated_content_type": (values.get("generated_content") or {}).get("type"),
        },
        "checkpoints": checkpoints,
        "checkpoints_truncated": len(history) > history_limit,
        "reducers": REDUCERS,
    }
