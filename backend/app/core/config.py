"""Application settings, loaded from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]


def load_dotenv(path: Path) -> None:
    """Minimal .env loader. Real environment variables always win."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer, got {raw!r}") from exc


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be a number, got {raw!r}") from exc


@dataclass(frozen=True)
class Settings:
    data_dir: Path

    # --- LLM ---------------------------------------------------------------
    llm_provider: str = "ollama"  # ollama | openai | offline
    llm_fallback: str = "offline"  # offline | none
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    llm_timeout_s: float = 120.0
    llm_temperature: float = 0.4

    # --- Context management --------------------------------------------------
    context_token_budget: int = 3000
    max_message_tokens: int = 1200
    token_counter: str = "auto"  # auto | tiktoken | approx

    # --- App behaviour -------------------------------------------------------
    default_user_id: str = "demo-student"
    max_upload_bytes: int = 5 * 1024 * 1024
    max_document_chars: int = 200_000
    router_mode: str = "hybrid"  # hybrid | rules | llm
    memory_extraction: str = "rules"  # rules | hybrid
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")

    @property
    def checkpoint_db(self) -> Path:
        return self.data_dir / "checkpoints.db"

    @property
    def store_db(self) -> Path:
        return self.data_dir / "memory_store.db"

    @property
    def app_db(self) -> Path:
        return self.data_dir / "app.db"

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv(BACKEND_DIR / ".env")
        data_dir = Path(os.environ.get("STUDYMATE_DATA_DIR", str(BACKEND_DIR / "data"))).expanduser()
        origins = os.environ.get("CORS_ORIGINS")
        settings = cls(
            data_dir=data_dir,
            llm_provider=os.environ.get("LLM_PROVIDER", "ollama").lower(),
            llm_fallback=os.environ.get("LLM_FALLBACK", "offline").lower(),
            ollama_base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/"),
            ollama_model=os.environ.get("OLLAMA_MODEL", "llama3.2"),
            openai_base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
            openai_model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            llm_timeout_s=_float("LLM_TIMEOUT_S", 120.0),
            llm_temperature=_float("LLM_TEMPERATURE", 0.4),
            context_token_budget=_int("CONTEXT_TOKEN_BUDGET", 3000),
            max_message_tokens=_int("MAX_MESSAGE_TOKENS", 1200),
            token_counter=os.environ.get("TOKEN_COUNTER", "auto").lower(),
            default_user_id=os.environ.get("DEFAULT_USER_ID", "demo-student"),
            max_upload_bytes=_int("MAX_UPLOAD_BYTES", 5 * 1024 * 1024),
            max_document_chars=_int("MAX_DOCUMENT_CHARS", 200_000),
            router_mode=os.environ.get("ROUTER_MODE", "hybrid").lower(),
            memory_extraction=os.environ.get("MEMORY_EXTRACTION", "rules").lower(),
            cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip())
            if origins
            else cls.cors_origins,
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.llm_provider not in {"ollama", "openai", "offline"}:
            raise ValueError("LLM_PROVIDER must be one of: ollama, openai, offline")
        if self.llm_fallback not in {"offline", "none"}:
            raise ValueError("LLM_FALLBACK must be one of: offline, none")
        if self.router_mode not in {"hybrid", "rules", "llm"}:
            raise ValueError("ROUTER_MODE must be one of: hybrid, rules, llm")
        if self.memory_extraction not in {"rules", "hybrid"}:
            raise ValueError("MEMORY_EXTRACTION must be one of: rules, hybrid")
        if self.token_counter not in {"auto", "tiktoken", "approx"}:
            raise ValueError("TOKEN_COUNTER must be one of: auto, tiktoken, approx")
        if not 200 <= self.context_token_budget <= 200_000:
            raise ValueError("CONTEXT_TOKEN_BUDGET must be between 200 and 200000")
        if self.max_message_tokens < 50:
            raise ValueError("MAX_MESSAGE_TOKENS must be at least 50")
        if self.llm_provider == "openai" and not self.openai_api_key:
            raise ValueError("LLM_PROVIDER=openai requires OPENAI_API_KEY")
