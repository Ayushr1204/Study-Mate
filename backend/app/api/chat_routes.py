"""Conversations and chat execution."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from app.api.deps import get_runtime, get_user_id
from app.models.schemas import ChatMessage, ChatRequest, ChatResponse, ThreadCreate, ThreadDetail, ThreadRename, ThreadSummary
from app.runtime import Runtime
from app.services.runner import get_thread_messages, run_graph, serialize_message

router = APIRouter(tags=["conversations"])


def _summary(row: dict) -> ThreadSummary:
    return ThreadSummary(id=row["id"], title=row["title"], created_at=row["created_at"], updated_at=row["updated_at"])


@router.post("/threads", response_model=ThreadSummary, status_code=201, summary="Create a conversation (a new LangGraph thread)")
def create_thread(body: ThreadCreate | None = None, rt: Runtime = Depends(get_runtime), user: str = Depends(get_user_id)):
    return _summary(rt.db.create_thread(uuid.uuid4().hex, user, body.title if body else None))


@router.get("/threads", response_model=list[ThreadSummary], summary="List the user's conversations")
def list_threads(rt: Runtime = Depends(get_runtime), user: str = Depends(get_user_id)):
    return [_summary(r) for r in rt.db.list_threads(user)]


@router.get("/threads/{thread_id}", response_model=ThreadDetail, summary="Restore a conversation from its checkpoint")
def get_thread(thread_id: str, rt: Runtime = Depends(get_runtime), user: str = Depends(get_user_id)):
    row = rt.db.get_thread(user, thread_id)
    messages = [ChatMessage(**serialize_message(m, i)) for i, m in enumerate(get_thread_messages(rt, thread_id))]
    return ThreadDetail(**_summary(row).model_dump(), messages=messages, last_execution=rt.db.latest_execution(user, thread_id))


@router.patch("/threads/{thread_id}", response_model=ThreadSummary, summary="Rename a conversation")
def rename_thread(thread_id: str, body: ThreadRename, rt: Runtime = Depends(get_runtime), user: str = Depends(get_user_id)):
    return _summary(rt.db.rename_thread(user, thread_id, body.title))


@router.delete("/threads/{thread_id}", status_code=204, summary="Delete a conversation and its checkpoints")
def delete_thread(thread_id: str, rt: Runtime = Depends(get_runtime), user: str = Depends(get_user_id)):
    rt.db.get_thread(user, thread_id)
    with rt.thread_lock(thread_id):
        rt.checkpointer.delete_thread(thread_id)
        rt.db.delete_thread(user, thread_id)


@router.post("/chat", response_model=ChatResponse, summary="Send a message: runs the compiled LangGraph once")
def chat(body: ChatRequest, rt: Runtime = Depends(get_runtime), user: str = Depends(get_user_id)):
    if body.thread_id:
        row = rt.db.get_thread(user, body.thread_id)
    else:
        row = rt.db.create_thread(uuid.uuid4().hex, user, None)
    values, record = run_graph(rt, user_id=user, thread_id=row["id"], text=body.message, budget=body.context_budget)
    reply = values["messages"][-1]
    title = rt.db.get_thread(user, row["id"])["title"]
    return ChatResponse(
        thread_id=row["id"], title=title, message=ChatMessage(**serialize_message(reply, len(values["messages"]) - 1)), execution=record
    )
