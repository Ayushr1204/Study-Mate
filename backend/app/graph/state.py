"""Typed LangGraph state and its reducers.

Three channels use custom reducers (everything else is last-write-wins):

* ``messages``            -> ``add_messages``: appends new messages, replaces by id, never drops history.
* ``learning_insights``   -> ``merge_insights``: accumulates per-topic counters across turns/checkpoints.
* ``execution_metadata``  -> ``merge_execution_metadata``: appends node trace entries within one run,
                             and starts afresh when a node sends ``_reset`` (first node of every run).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

INTENTS = ("explanation", "quiz", "summarization", "preference", "general")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def make_insight(kind: str, topic: str, intent: str) -> dict[str, Any]:
    """Build one learning insight (a single observation)."""
    now = utcnow()
    return {"kind": kind, "topic": topic, "count": 1, "intents": [intent], "first_seen": now, "last_seen": now}


def merge_insights(existing: list[dict[str, Any]] | None, new: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Reducer: combine insight lists by (kind, topic) instead of overwriting.

    Repeating an observation increments ``count`` and unions ``intents`` while keeping ``first_seen``;
    new observations are appended. Inputs are never mutated.
    """
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for item in [*(existing or []), *(new or [])]:
        key = (item["kind"], item["topic"].strip().lower())
        if key in merged:
            cur = merged[key]
            cur["count"] += item.get("count", 1)
            cur["intents"] = sorted({*cur["intents"], *item.get("intents", [])})
            cur["last_seen"] = max(cur["last_seen"], item.get("last_seen", cur["last_seen"]))
        else:
            merged[key] = {**item, "intents": sorted(item.get("intents", [])), "count": item.get("count", 1)}
    return list(merged.values())


def merge_execution_metadata(existing: dict[str, Any] | None, update: dict[str, Any] | None) -> dict[str, Any]:
    """Reducer: append ``trace`` entries and shallow-merge other keys; ``_reset`` starts a new run."""
    update = update or {}
    base: dict[str, Any] = {} if update.get("_reset") else dict(existing or {})
    trace = [*base.get("trace", []), *update.get("trace", [])]
    merged = {**base, **{k: v for k, v in update.items() if k not in ("trace", "_reset")}}
    merged["trace"] = trace
    return merged


class StudyState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    user_id: str
    thread_id: str
    intent: str
    topic: str
    current_query: str
    forced_intent: str | None
    request_payload: dict[str, Any]
    student_profile: dict[str, Any]
    retrieved_memory: dict[str, Any]
    learning_insights: Annotated[list[dict[str, Any]], merge_insights]
    generated_content: dict[str, Any]
    context_statistics: dict[str, Any]
    execution_metadata: Annotated[dict[str, Any], merge_execution_metadata]
