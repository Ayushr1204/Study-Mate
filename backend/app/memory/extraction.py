"""Controlled extraction of long-term learning facts from a user message.

Only a small allow-list of structured facts is ever extracted (explanation style, programming language,
current subjects, learning preferences). Rules are deterministic and testable; an optional LLM pass
(MEMORY_EXTRACTION=hybrid) can fill gaps but its output is validated against the same allow-list.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.memory.profile import ProfileUpdates, clean_text

NEGATION = re.compile(r"\b(don'?t|do not|dislike|hate|never|not|no longer|stop)\b", re.I)
CUE = re.compile(
    r"\b(prefer|like|love|want|wish|learn best|learn better|works? best|works? better|helps? me|"
    r"(?:please )?(?:always|from now on)|please (?:explain|use|show|give)|i need)\b",
    re.I,
)

# (regex over a cue-bearing sentence) -> canonical value.
EXPLANATION_STYLES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"analog(?:y|ies)|real[- ]?(?:world|life) (?:examples?|scenarios?)|everyday (?:examples?|life)", re.I), "real-world analogies"),
    (re.compile(r"simple (?:language|terms|words)|plain (?:english|language)|eli5|like i'?m (?:five|5)|layman", re.I), "simple language"),
    (re.compile(r"\b(?:concise|brief|short answers?|to the point)\b", re.I), "concise"),
    (re.compile(r"\b(?:detailed|in[- ]depth|thorough|comprehensive)\b", re.I), "detailed"),
]
LEARNING_PREFS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"step[- ]by[- ]step", re.I), "step-by-step explanations"),
    (re.compile(r"\b(?:diagrams?|visuals?|visual aids?|charts?)\b", re.I), "visual diagrams"),
    (re.compile(r"\bcode (?:examples?|samples?|snippets?)\b|\bwith code\b", re.I), "code examples"),
    (re.compile(r"\bpractice (?:questions|problems)\b|\bquiz(?:zes)? me\b", re.I), "practice questions"),
    (re.compile(r"\b(?:summary|tl;?dr) first\b|\bsummaries first\b", re.I), "summary first"),
]

LANGUAGES = {
    "python": "Python", "java": "Java", "javascript": "JavaScript", "typescript": "TypeScript", "c++": "C++",
    "c#": "C#", "golang": "Go", "rust": "Rust", "kotlin": "Kotlin", "swift": "Swift", "ruby": "Ruby",
    "php": "PHP", "sql": "SQL", "scala": "Scala", "matlab": "MATLAB", "c": "C", "go": "Go", "r": "R",
}
_LANG_ALT = "|".join(re.escape(k) for k in sorted(LANGUAGES, key=len, reverse=True))
LANG_CUE = re.compile(
    rf"(?:i\s+(?:mostly\s+|mainly\s+|usually\s+)?(?:code|program|write\s+code|develop|work)\s+(?:in|with|using)|"
    rf"my\s+(?:favou?rite|preferred|main|primary)\s+(?:programming\s+)?language\s+is|"
    rf"(?:use|show|give|write)\s+(?:me\s+)?(?:the\s+)?(?:code\s+|examples?\s+|samples?\s+)?(?:examples?\s+)?(?:in|using|with)|"
    rf"prefer\s+(?:code\s+(?:examples?\s+)?)?(?:in|using|with)|prefer)\s+(?P<lang>{_LANG_ALT})(?![\w+#])",
    re.I,
)
SUBJECT_CUE = re.compile(
    r"(?:i(?:'m| am)\s+(?:currently\s+)?(?:studying|learning|taking|doing|revising)|"
    r"i\s+(?:study|am\s+studying)|my\s+(?:current\s+)?(?:subjects?|courses?|classes)\s+(?:are|include)|"
    r"this\s+(?:semester|term),?\s+i(?:'m| am)?\s+(?:studying|taking))\s+(?P<subs>[^.!?\n]+)",
    re.I,
)
SUBJECT_TAIL = re.compile(
    r"\s+(?:this|next)\s+(?:semester|term|year)\b.*$|\s+(?:right now|at (?:college|university|school)|currently)\b.*$", re.I
)
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_SPLIT.split(text) if s.strip()]


def _title_subject(s: str) -> str:
    words = s.strip(" ,.;:'\"").split()
    return " ".join(w if (w.isupper() and len(w) <= 6) or any(c.isupper() for c in w[1:]) else w.capitalize() for w in words)


def extract_rules(text: str) -> ProfileUpdates:
    updates = ProfileUpdates()
    for sentence in _sentences(text):
        has_cue = bool(CUE.search(sentence))
        negated = bool(NEGATION.search(sentence))
        if has_cue and not negated:
            for pattern, value in EXPLANATION_STYLES:
                if pattern.search(sentence):
                    updates.style = value  # latest statement wins
                    break
            for pattern, value in LEARNING_PREFS:
                if pattern.search(sentence) and value not in updates.learning_preferences:
                    updates.learning_preferences.append(value)
        if not negated:
            m = LANG_CUE.search(sentence)
            if m:
                updates.language = LANGUAGES[m.group("lang").lower()]
        m = SUBJECT_CUE.search(sentence)
        if m and not negated:
            raw = SUBJECT_TAIL.sub("", m.group("subs"))
            for part in re.split(r",|\band\b|&|/", raw):
                subject = _title_subject(re.sub(r"^(?:the|a|an|my)\s+", "", part.strip(), flags=re.I))
                if 2 <= len(subject) <= 40 and len(subject.split()) <= 5 and subject.lower() not in {s.lower() for s in updates.subjects}:
                    updates.subjects.append(subject)
            updates.subjects = updates.subjects[:8]
    return updates


LLM_EXTRACT_SYSTEM = (
    "Extract durable learning preferences from the student's message. Reply with JSON only, using exactly these keys: "
    '{"preferred_explanation_style": string|null, "preferred_programming_language": string|null, '
    '"current_subjects": string[], "learning_preferences": string[]}. '
    "Use null/[] when the message states nothing durable. Never include personal data or question content."
)


def validate_llm_extraction(raw: str) -> ProfileUpdates:
    """Parse and sanitise LLM output against the allow-list; anything malformed yields no updates."""
    try:
        start, end = raw.index("{"), raw.rindex("}") + 1
        data: dict[str, Any] = json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError):
        return ProfileUpdates()

    def scalar(v: Any) -> str | None:
        return clean_text(v) if isinstance(v, str) and 2 <= len(clean_text(v)) <= 40 else None

    def items(v: Any) -> list[str]:
        if not isinstance(v, list):
            return []
        return [clean_text(x) for x in v if isinstance(x, str) and 2 <= len(clean_text(x)) <= 40][:5]

    lang = scalar(data.get("preferred_programming_language"))
    return ProfileUpdates(
        style=scalar(data.get("preferred_explanation_style")),
        language=LANGUAGES.get(lang.lower(), lang) if lang and lang.lower() in LANGUAGES else None,
        subjects=items(data.get("current_subjects")),
        learning_preferences=items(data.get("learning_preferences")),
    )


def looks_like_preference(text: str) -> bool:
    return bool(re.search(r"\b(prefer|like|love|always|favou?rite|studying|learning|taking|i'?m|i am|my|best)\b", text, re.I))
