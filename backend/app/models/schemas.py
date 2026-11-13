"""Request / response schemas for the REST API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

Difficulty = Literal["easy", "medium", "hard"]
SummaryPart = Literal["summary", "concepts", "revision", "terms"]
SummaryLength = Literal["short", "medium", "detailed"]


# ---------------------------------------------------------------- requests
class ThreadCreate(BaseModel):
    title: str | None = Field(default=None, max_length=80)

    @field_validator("title")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return v.strip() or None if v else None


class ThreadRename(BaseModel):
    title: str = Field(min_length=1, max_length=80)

    @field_validator("title")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("title must not be blank")
        return v


class ChatRequest(BaseModel):
    thread_id: str | None = None
    message: str = Field(min_length=1, max_length=30_000)
    context_budget: int | None = Field(default=None, ge=200, le=32_000, description="Override the token budget for this request.")

    @field_validator("message")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("message must not be blank")
        return v


class QuizGenerateRequest(BaseModel):
    topic: str = Field(min_length=2, max_length=120)
    difficulty: Difficulty = "medium"
    num_questions: int = Field(default=5, ge=1, le=15)
    context_budget: int | None = Field(default=None, ge=200, le=32_000)

    @field_validator("topic")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 2:
            raise ValueError("topic is too short")
        return v


class QuizSubmitRequest(BaseModel):
    answers: list[int | None] = Field(max_length=15)


class SummarizeRequest(BaseModel):
    text: str = Field(min_length=50, max_length=400_000)
    include: list[SummaryPart] = Field(default_factory=lambda: ["summary", "concepts", "revision", "terms"], min_length=1)
    length: SummaryLength = "medium"
    context_budget: int | None = Field(default=None, ge=200, le=32_000)


class MemoryPatch(BaseModel):
    preferred_explanation_style: str | None = Field(default=None, max_length=60)
    preferred_programming_language: str | None = Field(default=None, max_length=60)
    current_subjects: list[str] | None = Field(default=None, max_length=20)
    learning_preferences: list[str] | None = Field(default=None, max_length=20)
    revision_areas: list[str] | None = Field(default=None, max_length=20)


# --------------------------------------------------------------- responses
class HealthResponse(BaseModel):
    status: str
    version: str
    llm: dict[str, Any]
    token_counter: str
    context_token_budget: int
    default_user_id: str


class ThreadSummary(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class ChatMessage(BaseModel):
    id: str | None
    index: int | None = None
    role: str
    content: str
    created_at: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class ThreadDetail(ThreadSummary):
    messages: list[ChatMessage]
    last_execution: dict[str, Any] | None = None


class ChatResponse(BaseModel):
    thread_id: str
    title: str
    message: ChatMessage
    execution: dict[str, Any]


class QuizQuestionPublic(BaseModel):
    question: str
    options: list[str]


class QuizResponse(BaseModel):
    quiz_id: str
    topic: str
    difficulty: str
    requested: int
    questions: list[QuizQuestionPublic]
    warnings: list[str] = Field(default_factory=list)
    execution: dict[str, Any]


class QuizResultItem(BaseModel):
    question: str
    options: list[str]
    selected: int | None
    correct: int
    is_correct: bool
    explanation: str


class QuizResultResponse(BaseModel):
    quiz_id: str
    topic: str
    score: int
    total: int
    percent: int
    results: list[QuizResultItem]
    needs_revision: bool


class SummaryResponse(BaseModel):
    title: str
    summary: str
    key_concepts: list[str]
    revision_notes: list[str]
    key_terms: list[dict[str, str]]
    processing: dict[str, Any]
    execution: dict[str, Any]


class DocumentExtractResponse(BaseModel):
    text: str
    info: dict[str, Any]


class MemoryResponse(BaseModel):
    user_id: str
    namespace: list[str]
    key: str
    found: bool
    created_at: str | None
    updated_at: str | None
    profile: dict[str, Any]
