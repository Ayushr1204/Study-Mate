"""Pydantic models for structured LLM output (quiz and summary)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class QuizQuestion(BaseModel):
    question: str
    options: list[str]
    answer_index: int
    explanation: str = ""

    @field_validator("question")
    @classmethod
    def _q(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 5:
            raise ValueError("question text is too short")
        return v

    @model_validator(mode="after")
    def _check(self) -> QuizQuestion:
        self.options = [o.strip() for o in self.options]
        if len(self.options) != 4 or any(not o for o in self.options):
            raise ValueError("each question needs exactly 4 non-empty options")
        if len({o.lower() for o in self.options}) != 4:
            raise ValueError("options must be distinct")
        if not 0 <= self.answer_index < 4:
            raise ValueError("answer_index must be between 0 and 3")
        return self


class GeneratedQuiz(BaseModel):
    topic: str = ""
    questions: list[QuizQuestion] = Field(min_length=1)


class KeyTerm(BaseModel):
    term: str
    definition: str = ""


class SummaryOutput(BaseModel):
    title: str = ""
    summary: str = ""
    key_concepts: list[str] = Field(default_factory=list)
    revision_notes: list[str] = Field(default_factory=list)
    key_terms: list[KeyTerm] = Field(default_factory=list)

    @field_validator("key_concepts", "revision_notes", mode="before")
    @classmethod
    def _stringify(cls, v: Any) -> Any:
        if isinstance(v, list):
            return [x if isinstance(x, str) else str(x.get("text") or x.get("concept") or x) if isinstance(x, dict) else str(x) for x in v]
        return v

    @field_validator("key_terms", mode="before")
    @classmethod
    def _terms(cls, v: Any) -> Any:
        if isinstance(v, dict):
            return [{"term": k, "definition": str(d)} for k, d in v.items()]
        if isinstance(v, list):
            return [{"term": x, "definition": ""} if isinstance(x, str) else x for x in v]
        return v

    @field_validator("summary", mode="before")
    @classmethod
    def _summary(cls, v: Any) -> Any:
        return "\n".join(map(str, v)) if isinstance(v, list) else v


def normalize_quiz(data: dict[str, Any]) -> dict[str, Any]:
    """Tolerate common small-model deviations (letter answers, 'answer' text, wrong key names)."""
    questions = data.get("questions") or data.get("quiz") or []
    fixed = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        q = dict(q)
        opts = q.get("options") or q.get("choices") or []
        if isinstance(opts, dict):
            opts = [str(v) for _, v in sorted(opts.items())]
        opts = [str(o) for o in opts]
        q["options"] = opts
        idx = q.get("answer_index", q.get("correct_index", q.get("answer", q.get("correct_answer"))))
        if isinstance(idx, str):
            s = idx.strip()
            if s.isdigit():
                idx = int(s)
            elif len(s) == 1 and s.upper() in "ABCD":
                idx = "ABCD".index(s.upper())
            else:
                match = next((i for i, o in enumerate(opts) if o.strip().lower() == s.lower()), None)
                idx = match if match is not None else -1
        q["answer_index"] = idx if isinstance(idx, int) else -1
        fixed.append(q)
    return {"topic": str(data.get("topic") or data.get("title") or ""), "questions": fixed}
