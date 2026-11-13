"""LLM provider layer, token counting and the optional live integration test."""

from __future__ import annotations

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.core.config import Settings
from app.core.errors import LLMResponseError, LLMUnavailableError
from app.core.tokens import TokenCounter
from app.llm.base import to_chat_dicts
from app.llm.offline import OfflineProvider
from app.llm.providers import FallbackProvider, OllamaProvider, OpenAICompatProvider, build_provider


class FakeResponse:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code, self._payload, self.text = status, payload, text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("bad", request=None, response=None)  # type: ignore[arg-type]


MSGS = [SystemMessage("sys"), HumanMessage("hi"), AIMessage("yo"), HumanMessage("q")]


def test_message_conversion():
    assert [d["role"] for d in to_chat_dicts(MSGS)] == ["system", "user", "assistant", "user"]


def test_ollama_success_sends_expected_request(monkeypatch):
    seen = {}

    def fake_post(url, json, timeout):
        seen.update(url=url, body=json)
        return FakeResponse(payload={"message": {"content": "hello"}, "prompt_eval_count": 12, "eval_count": 3})

    monkeypatch.setattr(httpx, "post", fake_post)
    res = OllamaProvider("http://h:1/", "llama3.2", 5, 0.1).invoke(MSGS, json_mode=True)
    assert res.text == "hello" and (res.prompt_tokens, res.completion_tokens) == (12, 3) and res.provider == "ollama"
    assert seen["url"] == "http://h:1/api/chat" and seen["body"]["format"] == "json" and seen["body"]["stream"] is False
    assert seen["body"]["options"]["temperature"] == 0.1 and len(seen["body"]["messages"]) == 4


@pytest.mark.parametrize("status, needle", [(404, "no model named"), (500, "HTTP 500")])
def test_ollama_http_errors_give_helpful_messages(monkeypatch, status, needle):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse(status, text="boom"))
    with pytest.raises(LLMUnavailableError) as e:
        OllamaProvider("http://h", "m", 5, 0.1).invoke(MSGS)
    assert needle in e.value.message and e.value.hint


def test_ollama_unreachable_and_bad_shape(monkeypatch):
    def refuse(*a, **k):
        raise httpx.ConnectError("no")

    monkeypatch.setattr(httpx, "post", refuse)
    with pytest.raises(LLMUnavailableError) as e:
        OllamaProvider("http://h", "llama3.2", 5, 0.1).invoke(MSGS)
    assert "ollama serve" in e.value.hint and "ollama pull llama3.2" in e.value.hint
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse(payload={"unexpected": 1}))
    with pytest.raises(LLMResponseError):
        OllamaProvider("http://h", "m", 5, 0.1).invoke(MSGS)


def test_ollama_status_reports_missing_model(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: FakeResponse(payload={"models": [{"name": "mistral:latest"}]}))
    st = OllamaProvider("http://h", "llama3.2", 5, 0.1).status()
    assert st["reachable"] and not st["model_available"] and "ollama pull llama3.2" in st["hint"]
    monkeypatch.setattr(httpx, "get", lambda *a, **k: FakeResponse(payload={"models": [{"name": "llama3.2:latest"}]}))
    assert OllamaProvider("http://h", "llama3.2", 5, 0.1).status()["model_available"]


def test_openai_compat_provider(monkeypatch):
    seen = {}

    def fake_post(url, json, headers, timeout):
        seen.update(url=url, body=json, headers=headers)
        return FakeResponse(payload={"choices": [{"message": {"content": "ok"}}], "usage": {"prompt_tokens": 5, "completion_tokens": 2}})

    monkeypatch.setattr(httpx, "post", fake_post)
    res = OpenAICompatProvider("https://api.x/v1", "k", "gpt", 5, 0.2).invoke(MSGS, json_mode=True)
    assert res.text == "ok" and res.prompt_tokens == 5
    assert seen["url"].endswith("/chat/completions") and seen["headers"]["Authorization"] == "Bearer k"
    assert seen["body"]["response_format"] == {"type": "json_object"}
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse(401))
    with pytest.raises(LLMUnavailableError, match="credentials"):
        OpenAICompatProvider("https://api.x/v1", "bad", "gpt", 5, 0.2).invoke(MSGS)


def test_fallback_provider_circuit_breaker_and_task_support(monkeypatch):
    calls = {"n": 0}

    class Down:
        name, model, is_offline = "ollama", "m", False

        def invoke(self, *a, **k):
            calls["n"] += 1
            raise LLMUnavailableError("down")

        def status(self):
            return {"reachable": False}

    fb = FallbackProvider(Down(), OfflineProvider())  # type: ignore[arg-type]
    res = fb.invoke(MSGS, task="explain", hints={"query": "explain deadlock"})
    assert res.provider == "offline" and res.fallback_reason == "down" and "Deadlock" in res.text
    fb.invoke(MSGS, task="explain", hints={"query": "explain deadlock"})
    assert calls["n"] == 1, "primary is skipped while the breaker is open"
    with pytest.raises(LLMUnavailableError):  # offline cannot classify -> surfaced, not faked
        fb.invoke(MSGS, task="classify")


def test_build_provider_variants(tmp_path):
    base = dict(data_dir=tmp_path)
    assert build_provider(Settings(**base, llm_provider="offline")).is_offline
    assert isinstance(build_provider(Settings(**base, llm_provider="ollama", llm_fallback="none")), OllamaProvider)
    assert isinstance(build_provider(Settings(**base, llm_provider="ollama")), FallbackProvider)
    assert isinstance(build_provider(Settings(**base, llm_provider="openai", openai_api_key="k", llm_fallback="none")), OpenAICompatProvider)


@pytest.mark.parametrize("kwargs, msg", [
    (dict(llm_provider="bogus"), "LLM_PROVIDER"), (dict(context_token_budget=10), "CONTEXT_TOKEN_BUDGET"),
    (dict(llm_provider="openai"), "OPENAI_API_KEY"), (dict(router_mode="x"), "ROUTER_MODE"),
])
def test_settings_validation(tmp_path, kwargs, msg):
    with pytest.raises(ValueError, match=msg):
        Settings(data_dir=tmp_path, **kwargs).validate()


def test_settings_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDYMATE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CONTEXT_TOKEN_BUDGET", "1234")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5")
    s = Settings.from_env()
    assert s.context_token_budget == 1234 and s.ollama_model == "qwen2.5" and s.data_dir == tmp_path
    monkeypatch.setenv("CONTEXT_TOKEN_BUDGET", "abc")
    with pytest.raises(ValueError):
        Settings.from_env()


# --------------------------------------------------------------------- tokens
def test_token_counter_approx_is_deterministic():
    c = TokenCounter("approx")
    assert c.count_text("") == 0 and c.count_text("abcd") == 1 and c.count_text("abcde") == 2 and not c.exact
    assert c.count_message(HumanMessage("abcdefgh")) == 2 + 4
    assert c.count_messages([HumanMessage("abcd"), AIMessage("abcd")]) == 2 * (1 + 4)


def test_token_counter_auto_never_raises_without_network():
    c = TokenCounter("auto")
    assert c.name in ("approx:chars/4", "tiktoken:cl100k_base") and c.count_text("hello world") >= 2


# ------------------------------------------------------------ live integration
def _ollama_ready() -> tuple[bool, str]:
    s = Settings.from_env()
    st = OllamaProvider(s.ollama_base_url, s.ollama_model, 5, 0.1).status()
    return bool(st.get("reachable") and st.get("model_available")), s.ollama_model


_ready, _model = _ollama_ready()


@pytest.mark.integration
@pytest.mark.skipif(not _ready, reason="no reachable Ollama with the configured model")
def test_live_ollama_end_to_end(tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app
    from tests.conftest import chat, make_settings

    s = make_settings(tmp_path, llm_provider="ollama", llm_fallback="none", ollama_model=_model)
    with TestClient(create_app(s)) as c:
        body = chat(c, "In two sentences, what is a deadlock?")
        assert body["message"]["meta"]["provider"] == "ollama" and len(body["message"]["content"]) > 20
        quiz = c.post("/api/quiz/generate", json={"topic": "binary search", "num_questions": 2})
        assert quiz.status_code == 200 and len(quiz.json()["questions"]) >= 1
