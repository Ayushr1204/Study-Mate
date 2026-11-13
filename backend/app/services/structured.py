"""Calling the LLM for JSON output with validation and one corrective retry."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any, TypeVar

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from pydantic import BaseModel, ValidationError

from app.core.errors import LLMResponseError
from app.llm.base import LLMProvider, LLMResult

T = TypeVar("T", bound=BaseModel)


def parse_json_loose(text: str) -> dict[str, Any]:
    """Parse a JSON object from model output that may be wrapped in prose or code fences."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("no JSON object found in the model output") from None
        data = json.loads(cleaned[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    return data


def call_json(
    llm: LLMProvider,
    messages: list[BaseMessage],
    model_cls: type[T],
    *,
    task: str,
    hints: dict[str, Any] | None = None,
    normalize: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    retries: int = 1,
    temperature: float = 0.3,
) -> tuple[T, LLMResult, int]:
    """Returns (validated model, last LLMResult, attempts)."""
    convo = list(messages)
    last_error = ""
    for attempt in range(1, retries + 2):
        result = llm.invoke(convo, task=task, json_mode=True, temperature=temperature, hints=hints)
        try:
            data = parse_json_loose(result.text)
            if normalize:
                data = normalize(data)
            return model_cls.model_validate(data), result, attempt
        except (ValueError, ValidationError) as exc:
            last_error = str(exc).splitlines()[0][:200]
            convo = [
                *convo,
                AIMessage(content=result.text),
                HumanMessage(content=f"That reply was invalid ({last_error}). Reply again with ONLY valid JSON in the required shape."),
            ]
    raise LLMResponseError(
        f"The model did not return valid {task} JSON after {retries + 1} attempts ({last_error}).",
        hint="Try again, or switch to a more capable OLLAMA_MODEL.",
    )
