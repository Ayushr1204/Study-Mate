"""Long-term memory: a structured student profile in a LangGraph Store.

Namespace layout (one namespace per user, so users can never read each other's memory):

    ("users", <user_id>, "profile")  ->  key "profile"  ->  StudentProfile as a dict

Only structured, validated learning facts are stored - never raw conversation text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from langgraph.store.base import BaseStore
from pydantic import BaseModel, Field, field_validator

PROFILE_KEY = "profile"
MAX_ITEMS = 20
MAX_LEN = 60


def namespace_for(user_id: str) -> tuple[str, str, str]:
    return ("users", user_id, "profile")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_text(value: str) -> str:
    return " ".join(str(value).split())[:MAX_LEN].strip()


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        c = clean_text(v)
        if c and c.lower() not in seen:
            seen.add(c.lower())
            out.append(c)
    return out[:MAX_ITEMS]


class TopicRecord(BaseModel):
    topic: str
    count: int = 1
    last_studied: str = Field(default_factory=now_iso)

    @field_validator("topic")
    @classmethod
    def _clean(cls, v: str) -> str:
        return clean_text(v)


class StudentProfile(BaseModel):
    preferred_explanation_style: str | None = None
    preferred_programming_language: str | None = None
    current_subjects: list[str] = Field(default_factory=list)
    learning_preferences: list[str] = Field(default_factory=list)
    topics_studied: list[TopicRecord] = Field(default_factory=list)
    revision_areas: list[str] = Field(default_factory=list)
    updated_at: str | None = None

    @field_validator("preferred_explanation_style", "preferred_programming_language")
    @classmethod
    def _scalar(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = clean_text(v)
        return v or None

    @field_validator("current_subjects", "learning_preferences", "revision_areas")
    @classmethod
    def _lists(cls, v: list[str]) -> list[str]:
        return _dedupe(v)

    @field_validator("topics_studied")
    @classmethod
    def _topics(cls, v: list[TopicRecord]) -> list[TopicRecord]:
        return v[-MAX_ITEMS * 2 :]

    def is_empty(self) -> bool:
        return not (
            self.preferred_explanation_style
            or self.preferred_programming_language
            or self.current_subjects
            or self.learning_preferences
            or self.topics_studied
            or self.revision_areas
        )


# Fields a user (or the extractor) may set directly. Everything else is system-managed.
EDITABLE_SCALARS = ("preferred_explanation_style", "preferred_programming_language")
EDITABLE_LISTS = ("current_subjects", "learning_preferences", "revision_areas")


@dataclass
class ProfileUpdates:
    """Structured facts extracted from one user turn."""

    style: str | None = None
    language: str | None = None
    subjects: list[str] = field(default_factory=list)
    learning_preferences: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.style or self.language or self.subjects or self.learning_preferences)

    def describe(self) -> list[str]:
        out = []
        if self.style:
            out.append(f"Explanation style: {self.style}")
        if self.language:
            out.append(f"Programming language: {self.language}")
        if self.subjects:
            out.append("Current subjects: " + ", ".join(self.subjects))
        if self.learning_preferences:
            out.append("Learning preferences: " + ", ".join(self.learning_preferences))
        return out


class ProfileManager:
    def __init__(self, store: BaseStore):
        self.store = store

    # ---------------------------------------------------------------- reading
    def get(self, user_id: str) -> StudentProfile:
        item = self.store.get(namespace_for(user_id), PROFILE_KEY)
        return StudentProfile.model_validate(item.value) if item else StudentProfile()

    def inspect(self, user_id: str) -> dict[str, Any]:
        ns = namespace_for(user_id)
        item = self.store.get(ns, PROFILE_KEY)
        profile = StudentProfile.model_validate(item.value) if item else StudentProfile()
        return {
            "user_id": user_id,
            "namespace": list(ns),
            "key": PROFILE_KEY,
            "found": item is not None,
            "created_at": item.created_at.isoformat() if item else None,
            "updated_at": item.updated_at.isoformat() if item else None,
            "profile": profile.model_dump(),
        }

    # ---------------------------------------------------------------- writing
    def _save(self, user_id: str, profile: StudentProfile) -> StudentProfile:
        profile.updated_at = now_iso()
        self.store.put(namespace_for(user_id), PROFILE_KEY, profile.model_dump())
        return profile

    def apply_updates(self, user_id: str, updates: ProfileUpdates) -> tuple[StudentProfile, list[dict[str, Any]]]:
        """Merge extracted facts into the stored profile. Returns (profile, list of real changes)."""
        profile = self.get(user_id)
        changes: list[dict[str, Any]] = []

        if updates.style and clean_text(updates.style) != (profile.preferred_explanation_style or ""):
            changes.append({"field": "preferred_explanation_style", "action": "set",
                            "old": profile.preferred_explanation_style, "new": clean_text(updates.style)})
            profile.preferred_explanation_style = updates.style
        if updates.language and clean_text(updates.language) != (profile.preferred_programming_language or ""):
            changes.append({"field": "preferred_programming_language", "action": "set",
                            "old": profile.preferred_programming_language, "new": clean_text(updates.language)})
            profile.preferred_programming_language = updates.language
        for fld, values in (("current_subjects", updates.subjects), ("learning_preferences", updates.learning_preferences)):
            seen = {v.lower() for v in getattr(profile, fld)}
            added = []
            for v in map(clean_text, values):
                if v and v.lower() not in seen:
                    seen.add(v.lower())
                    added.append(v)
            if added:
                setattr(profile, fld, [*getattr(profile, fld), *added])
                changes.extend({"field": fld, "action": "add", "new": a} for a in added)

        if changes:
            profile = self._save(user_id, StudentProfile.model_validate(profile.model_dump()))
        return profile, changes

    def record_topic(self, user_id: str, topic: str) -> StudentProfile:
        topic = clean_text(topic)
        profile = self.get(user_id)
        if not topic:
            return profile
        for rec in profile.topics_studied:
            if rec.topic.lower() == topic.lower():
                rec.count += 1
                rec.last_studied = now_iso()
                break
        else:
            profile.topics_studied.append(TopicRecord(topic=topic))
        return self._save(user_id, StudentProfile.model_validate(profile.model_dump()))

    def update_revision(self, user_id: str, topic: str, needs_revision: bool) -> StudentProfile:
        topic = clean_text(topic)
        profile = self.get(user_id)
        current = [t for t in profile.revision_areas if t.lower() != topic.lower()]
        if needs_revision and topic:
            current.append(topic)
        profile.revision_areas = current
        return self._save(user_id, StudentProfile.model_validate(profile.model_dump()))

    def patch(self, user_id: str, fields: dict[str, Any]) -> StudentProfile:
        """User-driven edit of editable fields (replaces the provided fields)."""
        profile = self.get(user_id)
        data = profile.model_dump()
        for name, value in fields.items():
            if name in EDITABLE_SCALARS or name in EDITABLE_LISTS:
                data[name] = value
        return self._save(user_id, StudentProfile.model_validate(data))

    def remove(self, user_id: str, fld: str, value: str | None = None) -> StudentProfile:
        profile = self.get(user_id)
        data = profile.model_dump()
        if fld in EDITABLE_SCALARS:
            data[fld] = None
        elif fld in EDITABLE_LISTS + ("topics_studied",):
            if value is None:
                data[fld] = []
            elif fld == "topics_studied":
                data[fld] = [t for t in data[fld] if t["topic"].lower() != value.lower()]
            else:
                data[fld] = [v for v in data[fld] if v.lower() != value.lower()]
        else:
            raise KeyError(fld)
        return self._save(user_id, StudentProfile.model_validate(data))

    def clear(self, user_id: str) -> bool:
        ns = namespace_for(user_id)
        existed = self.store.get(ns, PROFILE_KEY) is not None
        self.store.delete(ns, PROFILE_KEY)
        return existed
