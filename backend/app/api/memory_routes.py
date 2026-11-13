"""Long-term memory inspection and management (LangGraph Store)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.api.deps import get_runtime, get_user_id
from app.core.errors import NotFoundError
from app.models.schemas import MemoryPatch, MemoryResponse
from app.runtime import Runtime

router = APIRouter(tags=["long-term memory"])


@router.get("/memory", response_model=MemoryResponse, summary="Inspect the stored student profile")
def get_memory(rt: Runtime = Depends(get_runtime), user: str = Depends(get_user_id)):
    return rt.profiles.inspect(user)


@router.patch("/memory", response_model=MemoryResponse, summary="Update editable profile fields")
def patch_memory(body: MemoryPatch, rt: Runtime = Depends(get_runtime), user: str = Depends(get_user_id)):
    fields = body.model_dump(exclude_unset=True)
    if fields:
        rt.profiles.patch(user, fields)
    return rt.profiles.inspect(user)


@router.delete("/memory/{field}", response_model=MemoryResponse, summary="Delete one field (or one list item with ?value=)")
def delete_memory_field(field: str, value: str | None = None, rt: Runtime = Depends(get_runtime), user: str = Depends(get_user_id)):
    try:
        rt.profiles.remove(user, field, value)
    except KeyError:
        raise NotFoundError(f"Unknown memory field '{field}'.") from None
    return rt.profiles.inspect(user)


@router.delete("/memory", status_code=204, summary="Delete the entire stored profile")
def clear_memory(rt: Runtime = Depends(get_runtime), user: str = Depends(get_user_id)):
    rt.profiles.clear(user)
    return Response(status_code=204)


@router.delete("/user/data", summary="Delete ALL of this user's data (profile, conversations, quizzes)")
def delete_user_data(rt: Runtime = Depends(get_runtime), user: str = Depends(get_user_id)):
    rt.profiles.clear(user)
    thread_ids = rt.db.purge_user(user)
    for tid in thread_ids:
        rt.checkpointer.delete_thread(tid)
    return {"deleted_threads": len(thread_ids), "profile_deleted": True}
