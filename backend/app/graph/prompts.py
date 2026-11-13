"""Prompt construction. Personalisation comes ONLY from the long-term profile loaded by load_memory_node."""

from __future__ import annotations

from typing import Any

BASE_SYSTEM = """You are StudyMate, a patient, accurate AI study assistant for students.
- Answer in clear Markdown: short paragraphs, headings when helpful, lists and tables where they aid understanding.
- Put code in fenced blocks with a language tag. Write mathematics in LaTeX: inline $...$ and display $$...$$.
- Be correct first. If you are unsure, say so. Never invent citations or facts.
- Use earlier turns of the conversation when they are relevant (follow-up questions, "simplify that", "give an example")."""


def personalization(profile: dict[str, Any], insights: list[dict[str, Any]] | None = None) -> str:
    lines: list[str] = []
    if profile.get("preferred_explanation_style"):
        lines.append(
            f"- Preferred explanation style: **{profile['preferred_explanation_style']}**. "
            "Apply it in this answer (for example, if it is 'real-world analogies', build the explanation around a concrete everyday analogy)."
        )
    if profile.get("preferred_programming_language"):
        lines.append(f"- Preferred programming language: {profile['preferred_programming_language']}. Use it for any code examples.")
    if profile.get("current_subjects"):
        lines.append("- Current subjects: " + ", ".join(profile["current_subjects"]) + ".")
    if profile.get("learning_preferences"):
        lines.append("- Learning preferences: " + ", ".join(profile["learning_preferences"]) + ". Honour them.")
    if profile.get("revision_areas"):
        lines.append("- Needs revision on: " + ", ".join(profile["revision_areas"]) + ".")
    topics = [i for i in (insights or []) if i.get("kind") == "topic"]
    if topics:
        recent = sorted(topics, key=lambda i: i["last_seen"], reverse=True)[:5]
        lines.append("- Topics already covered in this conversation: " + ", ".join(f"{t['topic']} (x{t['count']})" for t in recent) + ".")
    if not lines:
        return ""
    return "\n\n## What you know about this student (long-term memory - apply it)\n" + "\n".join(lines)


def quiz_system(topic: str, n: int, difficulty: str, profile: dict[str, Any]) -> str:
    lang = profile.get("preferred_programming_language")
    extra = f" Where code appears in questions, prefer {lang}." if lang else ""
    return (
        f"You write multiple-choice quizzes for students. Create exactly {n} questions about '{topic}' at {difficulty} difficulty."
        f"{extra}\nReply with JSON ONLY, in exactly this shape:\n"
        '{"topic": "short topic title", "questions": [{"question": "...", "options": ["A text", "B text", "C text", "D text"], '
        '"answer_index": 0, "explanation": "1-2 sentences on why the answer is right"}]}\n'
        "Rules: exactly 4 distinct options per question; exactly one correct option; answer_index is the 0-based index of "
        "the correct option; vary the position of the correct answer; no 'all of the above'; options contain no letter prefixes."
    )


LENGTH_WORDS = {"short": "2-3 sentences", "medium": "one short paragraph (4-6 sentences)", "detailed": "two or three paragraphs"}


def summary_system(include: list[str], length: str, profile: dict[str, Any]) -> str:
    wanted = {
        "summary": f'"summary": {LENGTH_WORDS.get(length, LENGTH_WORDS["medium"])} summarising the material',
        "concepts": '"key_concepts": array of 5-10 short concept names',
        "revision": '"revision_notes": array of concise bullet strings for last-minute revision',
        "terms": '"key_terms": array of {"term": "...", "definition": "..."} objects',
    }
    fields = [wanted[k] for k in include if k in wanted]
    style = profile.get("preferred_explanation_style")
    tone = f" Where it helps, favour this style: {style}." if style else ""
    return (
        "You turn study material into structured notes. Use ONLY information in the material; do not add outside facts."
        f"{tone}\nReply with JSON ONLY with keys: \"title\" (short topic title), "
        + ", ".join(fields)
        + ". Omit nothing that is requested; use empty arrays/strings for unrequested keys."
    )


CHUNK_SYSTEM = "Summarise this part of a longer document as 5-8 compact bullet points. Keep key terms and definitions. Reply with bullets only."

CLASSIFY_SYSTEM = (
    "Classify the student's message into exactly one intent: "
    '"explanation" (asks to explain/teach/compare/give examples), "quiz" (wants questions to practise), '
    '"summarization" (wants notes summarised), "preference" (states how they like to learn, without asking anything), '
    '"general" (greeting / small talk). Reply with JSON only: {"intent": "<one of those>"}.'
)
