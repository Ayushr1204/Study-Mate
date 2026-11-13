"""FastAPI dependencies: the runtime container and the acting user."""

from __future__ import annotations

import re

from fastapi import Header, Request

from app.core.errors import BadRequestError
from app.runtime import Runtime

USER_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


def get_runtime(request: Request) -> Runtime:
    return request.app.state.runtime


def get_user_id(request: Request, x_user_id: str | None = Header(default=None)) -> str:
    """The acting user comes from the X-User-Id header (no authentication: this is a local single-machine app).

    Memory namespaces and conversations are scoped by this id, so different ids are fully isolated.
    """
    user_id = (x_user_id or request.app.state.runtime.settings.default_user_id).strip()
    if not USER_ID_RE.match(user_id):
        raise BadRequestError("Invalid X-User-Id.", hint="Use 1-64 letters, digits, '.', '_' or '-'.")
    return user_id
