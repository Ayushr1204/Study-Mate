"""Concrete providers: Ollama (primary), OpenAI-compatible (optional) and a fallback wrapper."""

from __future__ import annotations

import time
from typing import Any

import httpx
from langchain_core.messages import BaseMessage

from app.core.config import Settings
from app.core.errors import LLMResponseError, LLMUnavailableError
from app.llm.base import LLMProvider, LLMResult, to_chat_dicts
from app.llm.offline import OfflineProvider


class OllamaProvider:
    name = "ollama"
    is_offline = False

    def __init__(self, base_url: str, model: str, timeout_s: float, temperature: float):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s
        self.temperature = temperature

    def _unreachable(self, exc: Exception) -> LLMUnavailableError:
        return LLMUnavailableError(
            f"Cannot reach Ollama at {self.base_url} ({type(exc).__name__}).",
            hint=f"Start it with `ollama serve`, then pull the model: `ollama pull {self.model}`. "
            "Or set OLLAMA_BASE_URL / OLLAMA_MODEL in backend/.env.",
        )

    def invoke(
        self,
        messages: list[BaseMessage],
        *,
        task: str = "chat",
        json_mode: bool = False,
        temperature: float | None = None,
        hints: dict[str, Any] | None = None,
    ) -> LLMResult:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": to_chat_dicts(messages),
            "stream": False,
            "options": {"temperature": self.temperature if temperature is None else temperature},
        }
        if json_mode:
            body["format"] = "json"
        started = time.perf_counter()
        try:
            resp = httpx.post(f"{self.base_url}/api/chat", json=body, timeout=self.timeout_s)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
            raise self._unreachable(exc) from exc
        if resp.status_code == 404:
            raise LLMUnavailableError(
                f"Ollama has no model named {self.model!r}.",
                hint=f"Run `ollama pull {self.model}` or change OLLAMA_MODEL.",
            )
        if resp.status_code >= 400:
            raise LLMUnavailableError(
                f"Ollama returned HTTP {resp.status_code}: {resp.text[:200]}",
                hint="Check the Ollama server logs.",
            )
        try:
            data = resp.json()
            text = data["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMResponseError("Ollama returned an unexpected response shape.") from exc
        return LLMResult(
            text=text,
            provider=self.name,
            model=self.model,
            prompt_tokens=data.get("prompt_eval_count"),
            completion_tokens=data.get("eval_count"),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    def status(self) -> dict[str, Any]:
        info: dict[str, Any] = {"provider": self.name, "model": self.model, "base_url": self.base_url}
        try:
            resp = httpx.get(f"{self.base_url}/api/tags", timeout=3.0)
            resp.raise_for_status()
            models = [m.get("name", "") for m in resp.json().get("models", [])]
        except Exception as exc:
            return {**info, "reachable": False, "model_available": False, "error": f"{type(exc).__name__}: {exc}",
                    "hint": f"Start Ollama (`ollama serve`) and run `ollama pull {self.model}`."}
        wanted = self.model if ":" in self.model else f"{self.model}:latest"
        available = any(m == self.model or m == wanted for m in models)
        return {**info, "reachable": True, "model_available": available, "installed_models": models,
                "hint": None if available else f"Run `ollama pull {self.model}`."}


class OpenAICompatProvider:
    name = "openai"
    is_offline = False

    def __init__(self, base_url: str, api_key: str, model: str, timeout_s: float, temperature: float):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s
        self.temperature = temperature

    def invoke(
        self,
        messages: list[BaseMessage],
        *,
        task: str = "chat",
        json_mode: bool = False,
        temperature: float | None = None,
        hints: dict[str, Any] | None = None,
    ) -> LLMResult:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": to_chat_dicts(messages),
            "temperature": self.temperature if temperature is None else temperature,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        started = time.perf_counter()
        try:
            resp = httpx.post(
                f"{self.base_url}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout_s,
            )
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
            raise LLMUnavailableError(
                f"Cannot reach the API at {self.base_url} ({type(exc).__name__}).",
                hint="Check OPENAI_BASE_URL and your network connection.",
            ) from exc
        if resp.status_code in (401, 403):
            raise LLMUnavailableError("The API rejected the credentials.", hint="Check OPENAI_API_KEY.")
        if resp.status_code >= 400:
            raise LLMUnavailableError(f"API returned HTTP {resp.status_code}: {resp.text[:200]}")
        try:
            data = resp.json()
            text = data["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError("The API returned an unexpected response shape.") from exc
        usage = data.get("usage") or {}
        return LLMResult(
            text=text,
            provider=self.name,
            model=self.model,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    def status(self) -> dict[str, Any]:
        info = {"provider": self.name, "model": self.model, "base_url": self.base_url}
        try:
            resp = httpx.get(
                f"{self.base_url}/models", headers={"Authorization": f"Bearer {self.api_key}"}, timeout=5.0
            )
            ok = resp.status_code < 400
            return {**info, "reachable": True, "model_available": ok, "error": None if ok else f"HTTP {resp.status_code}"}
        except Exception as exc:
            return {**info, "reachable": False, "model_available": False, "error": f"{type(exc).__name__}: {exc}"}


class FallbackProvider:
    """Tries the primary provider; on LLMUnavailableError uses the offline fallback if it can serve the task.

    A circuit breaker avoids re-trying a dead primary on every call of one request.
    """

    is_offline = False

    def __init__(self, primary: LLMProvider, fallback: OfflineProvider, cooldown_s: float = 10.0):
        self.primary = primary
        self.fallback = fallback
        self.cooldown_s = cooldown_s
        self._down_until = 0.0
        self._last_reason: str | None = None
        self.name = primary.name
        self.model = primary.model

    def invoke(
        self,
        messages: list[BaseMessage],
        *,
        task: str = "chat",
        json_mode: bool = False,
        temperature: float | None = None,
        hints: dict[str, Any] | None = None,
    ) -> LLMResult:
        if time.monotonic() >= self._down_until:
            try:
                return self.primary.invoke(
                    messages, task=task, json_mode=json_mode, temperature=temperature, hints=hints
                )
            except LLMUnavailableError as exc:
                self._down_until = time.monotonic() + self.cooldown_s
                self._last_reason = exc.message
                if not self.fallback.supports(task):
                    raise
        elif not self.fallback.supports(task):
            raise LLMUnavailableError(
                self._last_reason or "The language model is unavailable.",
                hint=f"Start Ollama and pull the model `{self.primary.model}`.",
            )
        result = self.fallback.invoke(messages, task=task, json_mode=json_mode, temperature=temperature, hints=hints)
        result.fallback_reason = self._last_reason
        return result

    def status(self) -> dict[str, Any]:
        status = self.primary.status()
        status["fallback"] = "offline"
        status["active"] = "primary" if status.get("reachable") and status.get("model_available") else "offline"
        return status


def build_provider(settings: Settings) -> LLMProvider:
    offline = OfflineProvider()
    if settings.llm_provider == "offline":
        return offline
    if settings.llm_provider == "ollama":
        primary: LLMProvider = OllamaProvider(
            settings.ollama_base_url, settings.ollama_model, settings.llm_timeout_s, settings.llm_temperature
        )
    else:
        primary = OpenAICompatProvider(
            settings.openai_base_url,
            settings.openai_api_key,
            settings.openai_model,
            settings.llm_timeout_s,
            settings.llm_temperature,
        )
    if settings.llm_fallback == "offline":
        return FallbackProvider(primary, offline)
    return primary
