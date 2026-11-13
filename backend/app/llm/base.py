"""Provider abstraction shared by every LLM backend."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Protocol

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.core.tokens import content_to_text


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: int = 0
    fallback_reason: str | None = None

    def meta(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("text")
        return d


class LLMProvider(Protocol):
    name: str
    model: str
    is_offline: bool

    def invoke(
        self,
        messages: list[BaseMessage],
        *,
        task: str = "chat",
        json_mode: bool = False,
        temperature: float | None = None,
        hints: dict[str, Any] | None = None,
    ) -> LLMResult: ...

    def status(self) -> dict[str, Any]: ...


def to_chat_dicts(messages: list[BaseMessage]) -> list[dict[str, str]]:
    """Convert LangChain messages to the role/content dicts both Ollama and OpenAI accept."""
    out: list[dict[str, str]] = []
    for m in messages:
        if isinstance(m, SystemMessage):
            role = "system"
        elif isinstance(m, HumanMessage):
            role = "user"
        elif isinstance(m, AIMessage):
            role = "assistant"
        else:
            role = "user"
        out.append({"role": role, "content": content_to_text(m.content)})
    return out
