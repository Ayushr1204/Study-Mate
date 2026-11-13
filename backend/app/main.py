"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api import chat_routes, inspect_routes, learning_routes, memory_routes
from app.core.config import Settings
from app.core.errors import StudyMateError
from app.llm.base import LLMProvider
from app.runtime import Runtime

log = logging.getLogger("studymate")


def create_app(settings: Settings | None = None, llm: LLMProvider | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.runtime = Runtime(settings, llm)
        log.info("StudyMate ready: provider=%s counter=%s data=%s", settings.llm_provider, app.state.runtime.counter.name, settings.data_dir)
        try:
            yield
        finally:
            app.state.runtime.close()

    app = FastAPI(
        title="StudyMate API",
        version=__version__,
        description="REST API for StudyMate - an AI study assistant built on a compiled LangGraph StateGraph "
        "(SQLite checkpointing, trimmed context, short- and long-term memory).",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["*"], allow_headers=["*"],
    )

    @app.exception_handler(StudyMateError)
    async def handle_domain_error(_: Request, exc: StudyMateError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, "hint": exc.hint, "node": getattr(exc, "studymate_node", None)}},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "validation_error", "message": f"{where}: {first.get('msg', 'invalid input')}".strip(": "),
                               "hint": None, "node": None}},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        log.exception("Unhandled error", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": f"{type(exc).__name__}: {exc}", "hint": "See the backend log.",
                               "node": getattr(exc, "studymate_node", None)}},
        )

    for module in (inspect_routes, chat_routes, learning_routes, memory_routes):
        app.include_router(module.router, prefix="/api")
    return app


def app_factory() -> FastAPI:
    """Entry point for `uvicorn app.main:app_factory --factory`."""
    logging.basicConfig(level=logging.INFO)
    return create_app()
