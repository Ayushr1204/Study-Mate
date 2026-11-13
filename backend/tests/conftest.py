"""Shared fixtures. All automated tests use a deterministic scripted LLM - no network, no Ollama."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import BaseMessage

from app.core.config import Settings
from app.llm.base import LLMResult
from app.main import create_app
from app.runtime import Runtime


@dataclass
class Call:
    task: str
    messages: list[BaseMessage]
    hints: dict[str, Any] | None

    @property
    def system(self) -> str:
        return str(self.messages[0].content)

    @property
    def history(self) -> list[BaseMessage]:
        return self.messages[1:]


@dataclass
class ScriptedLLM:
    """Deterministic stand-in for a real model. Records every call for assertions."""

    name: str = "scripted"
    model: str = "scripted-1"
    is_offline: bool = False
    calls: list[Call] = field(default_factory=list)
    fail_with: Exception | None = None
    classify_as: str = "explanation"
    extract_json: str = "{}"

    def invoke(self, messages, *, task="chat", json_mode=False, temperature=None, hints=None) -> LLMResult:
        self.calls.append(Call(task, list(messages), hints))
        if self.fail_with is not None:
            raise self.fail_with
        hints = hints or {}
        if task == "explain":
            text = f"EXPLAIN[{hints.get('style')}] {hints.get('query', '')}"
        elif task in ("general", "chat"):
            text = "ACK " + str(hints.get("intent"))
        elif task == "quiz":
            n = int(hints["n"])
            text = json.dumps({
                "topic": hints["topic"].title(),
                "questions": [
                    {"question": f"Question {i + 1} about {hints['topic']}?", "options": ["alpha", "beta", "gamma", "delta"],
                     "answer_index": i % 4, "explanation": f"Because {i}."}
                    for i in range(n)
                ],
            })
        elif task == "summarize":
            text = json.dumps({"title": "Scripted Summary Title", "summary": "A scripted summary.", "key_concepts": ["one", "two"],
                               "revision_notes": ["note"], "key_terms": [{"term": "t", "definition": "d"}]})
        elif task == "summarize_chunk":
            text = "- chunk note"
        elif task == "classify":
            text = json.dumps({"intent": self.classify_as})
        elif task == "extract":
            text = self.extract_json
        else:
            text = "ok"
        return LLMResult(text=text, provider=self.name, model=self.model, prompt_tokens=1, completion_tokens=1)

    def status(self) -> dict[str, Any]:
        return {"provider": self.name, "model": self.model, "reachable": True, "model_available": True}

    def calls_for(self, task: str) -> list[Call]:
        return [c for c in self.calls if c.task == task]


def make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    base = dict(data_dir=tmp_path / "data", llm_provider="offline", token_counter="approx",
                context_token_budget=3000, max_message_tokens=1200)
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def llm() -> ScriptedLLM:
    return ScriptedLLM()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def runtime(settings: Settings, llm: ScriptedLLM):
    rt = Runtime(settings, llm)
    yield rt
    rt.close()


@pytest.fixture
def client(settings: Settings, llm: ScriptedLLM):
    with TestClient(create_app(settings, llm)) as c:
        yield c


def chat(client: TestClient, message: str, thread_id: str | None = None, user: str | None = None, **extra: Any) -> dict[str, Any]:
    headers = {"X-User-Id": user} if user else {}
    r = client.post("/api/chat", json={"message": message, "thread_id": thread_id, **extra}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()
