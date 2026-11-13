"""Markdown rendering of structured results, used when a quiz/summary is requested inside a chat thread."""

from __future__ import annotations

from typing import Any

LETTERS = "ABCD"


def render_quiz_markdown(quiz: dict[str, Any]) -> str:
    out = [f"## Quiz: {quiz.get('topic', 'Practice questions')}", f"*{quiz.get('difficulty', 'medium')} difficulty, {len(quiz['questions'])} questions*", ""]
    for i, q in enumerate(quiz["questions"], 1):
        out.append(f"**{i}. {q['question']}**")
        out.extend(f"- {LETTERS[j]}. {opt}" for j, opt in enumerate(q["options"]))
        out.append("")
    out.append("### Answer key")
    for i, q in enumerate(quiz["questions"], 1):
        out.append(f"{i}. **{LETTERS[q['answer_index']]}** - {q.get('explanation', '')}".rstrip(" -"))
    for w in quiz.get("warnings", []):
        out.append(f"\n> {w}")
    return "\n".join(out)


def render_summary_markdown(s: dict[str, Any]) -> str:
    out = [f"## {s.get('title') or 'Summary'}"]
    if s.get("summary"):
        out += ["### Summary", s["summary"]]
    if s.get("key_concepts"):
        out += ["### Key concepts", "\n".join(f"- {c}" for c in s["key_concepts"])]
    if s.get("revision_notes"):
        out += ["### Revision notes", "\n".join(f"- {n}" for n in s["revision_notes"])]
    if s.get("key_terms"):
        rows = "\n".join(f"| {t['term']} | {t.get('definition', '').replace('|', '/')} |" for t in s["key_terms"])
        out += ["### Key terms", "| Term | Definition |\n|---|---|\n" + rows]
    return "\n\n".join(out)
