"""Intent classification helpers used by router_node."""

from __future__ import annotations

import re

QUIZ_RE = re.compile(r"\b(quiz|mcqs?|multiple[- ]choice|test me|practice (?:questions|problems)|flash ?cards?)\b", re.I)
SUMMARY_RE = re.compile(r"\b(summari[sz]e|summary of|tl;?dr|revision notes|key terms|condense|key takeaways)\b", re.I)
REQUEST_RE = re.compile(
    r"\b(explain|what is|what are|what's|how does|how do|how is|why does|why is|why do|tell me|describe|define|teach me|"
    r"difference between|compare|walk me through|help me understand|give me an? (?:example|analogy))\b|\?",
    re.I,
)
PREF_RE = re.compile(
    r"\b(i (?:really )?(?:prefer|like|love|learn best|learn better|work best|want you to)|please (?:always )?(?:explain|use|show)|"
    r"always (?:explain|use|show)|from now on|my (?:favou?rite|preferred|main) (?:programming )?language|"
    r"i(?:'m| am) (?:currently )?(?:studying|learning|taking)|i (?:code|program) in|my (?:current )?(?:subjects?|courses?) (?:are|include))\b",
    re.I,
)
GREETING_RE = re.compile(r"^\s*(hi|hello|hey|thanks|thank you|ok|okay|cool|great|good (?:morning|evening|afternoon))\b[\s!.]*$", re.I)

_LEAD = re.compile(
    r"^(?:please\s+)?(?:(?:can|could|would) you\s+)?(?:please\s+)?"
    r"(?:explain|describe|define|teach me|tell me about|what(?:'s| is| are)|how (?:does|do|is)|why (?:does|do|is)|"
    r"help me understand|walk me through|give me an? (?:example|analogy) (?:of|for))\s+(?:to me\s+)?"
    r"(?:the\s+)?(?:concept of\s+|idea of\s+|difference between\s+|an?\s+)?",
    re.I,
)
_TAIL = re.compile(r"\s+(?:using|with|in simple|in detail|in terms of|like i'?m|step by step|please|for me|to me|again|once more|one more time)\b.*$", re.I)


def classify_rules(text: str) -> tuple[str, str] | None:
    """Return (intent, reason) when the rules are confident, else None."""
    if QUIZ_RE.search(text):
        return "quiz", "matched quiz keywords"
    if SUMMARY_RE.search(text):
        return "summarization", "matched summarization keywords"
    has_request = bool(REQUEST_RE.search(text))
    if PREF_RE.search(text) and not has_request:
        return "preference", "statement of a learning preference"
    if has_request:
        return "explanation", "question / explanation request"
    if GREETING_RE.match(text):
        return "general", "greeting or acknowledgement"
    return None


def extract_topic(text: str) -> str:
    """Best-effort short topic phrase from a question (used for insights; may be empty)."""
    t = " ".join(text.strip().split()).rstrip("?.! ")
    t = t.split(". ")[-1] if ". " in t and REQUEST_RE.search(t.split(". ")[-1]) else t
    for _ in range(2):
        t = _LEAD.sub("", t).strip()
    t = _TAIL.sub("", t).strip(" ,;:")
    words = t.split()[:6]
    topic = " ".join(words).lower()
    return topic if 3 <= len(topic) <= 60 else ""


def extract_quiz_params(text: str) -> dict:
    """Pull topic / count / difficulty out of a free-text quiz request."""
    n_match = re.search(r"\b(\d{1,2})\s*(?:questions?|mcqs?|q\b)", text, re.I)
    diff = re.search(r"\b(easy|medium|hard)\b", text, re.I)
    topic_match = re.search(r"\b(?:on|about|covering|for)\s+(.+?)(?:\s+(?:with|using|at|\d+\s*questions?)\b|[.?!]|$)", text, re.I)
    topic = topic_match.group(1).strip() if topic_match else re.sub(QUIZ_RE, "", text).strip(" ,.?!")
    return {
        "topic": topic[:80] or "general knowledge",
        "n": min(max(int(n_match.group(1)), 1), 15) if n_match else 5,
        "difficulty": diff.group(1).lower() if diff else "medium",
    }
