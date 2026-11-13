"""Health, graph structure, state / execution inspection and the dashboard."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app import __version__
from app.api.deps import get_runtime, get_user_id
from app.graph.builder import describe_graph
from app.models.schemas import HealthResponse
from app.runtime import Runtime
from app.services.runner import inspect_thread_state

router = APIRouter(tags=["inspection"])


@router.get("/health", response_model=HealthResponse, summary="Liveness + configuration (no network calls)")
def health(rt: Runtime = Depends(get_runtime)):
    s = rt.settings
    model = s.ollama_model if s.llm_provider == "ollama" else s.openai_model if s.llm_provider == "openai" else rt.llm.model
    return HealthResponse(
        status="ok", version=__version__,
        llm={"provider": s.llm_provider, "model": model, "fallback": s.llm_fallback},
        token_counter=rt.counter.name, context_token_budget=s.context_token_budget, default_user_id=s.default_user_id,
    )


@router.get("/llm/status", summary="Actively probe the configured LLM provider")
def llm_status(rt: Runtime = Depends(get_runtime)):
    return rt.llm.status()


@router.get("/graph", summary="The REAL compiled graph (from graph.get_graph()) with node metadata and Mermaid source")
def graph_structure(rt: Runtime = Depends(get_runtime)):
    return describe_graph(rt.graph)


@router.get("/threads/{thread_id}/state", summary="Raw checkpoint / state inspection for a thread")
def thread_state(thread_id: str, rt: Runtime = Depends(get_runtime), user: str = Depends(get_user_id)):
    rt.db.get_thread(user, thread_id)
    return inspect_thread_state(rt, thread_id)


@router.get("/executions/latest", summary="Latest graph execution (optionally for one thread)")
def latest_execution(thread_id: str | None = None, rt: Runtime = Depends(get_runtime), user: str = Depends(get_user_id)):
    if thread_id:
        rt.db.get_thread(user, thread_id)
    return {"execution": rt.db.latest_execution(user, thread_id)}


@router.get("/executions", summary="Recent graph executions")
def executions(limit: int = 10, rt: Runtime = Depends(get_runtime), user: str = Depends(get_user_id)):
    return {"executions": rt.db.recent_executions(user, max(1, min(limit, 50)))}


@router.get("/dashboard", summary="Dashboard data - every figure is read from stored application data")
def dashboard(rt: Runtime = Depends(get_runtime), user: str = Depends(get_user_id)) -> dict[str, Any]:
    profile = rt.profiles.inspect(user)
    topics = sorted(profile["profile"]["topics_studied"], key=lambda t: t["last_studied"], reverse=True)[:8]
    threads = rt.db.list_threads(user)
    return {
        "user_id": user,
        "recent_threads": threads[:5],
        "thread_count": len(threads),
        "recent_topics": topics,
        "quiz": rt.db.quiz_activity(user),
        "profile": profile,
        "runs_by_intent": rt.db.execution_stats(user),
        "recent_executions": [
            {"request_id": e["request_id"], "thread_id": e["thread_id"], "intent": e.get("intent"), "status": e["status"],
             "created_at": e["created_at"], "duration_ms": e.get("duration_ms"), "kind": e.get("kind")}
            for e in rt.db.recent_executions(user, 5)
        ],
    }
