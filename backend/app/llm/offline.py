"""Offline fallback provider.

NOT a language model. It exists so the app (and the LangGraph mechanics it demonstrates) keeps working
when no LLM is reachable. It is deterministic and honest about it:

* explain / quiz: served from a tiny built-in knowledge base (six CS topics); other topics get a clear
  "no model connected" message.
* summarize: genuine extractive summarisation (sentence scoring by term frequency).
* classify / extract: unsupported - callers fall back to their rule-based logic.

Every result is tagged provider="offline" so the UI can show that a fallback answered.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter
from typing import Any

from langchain_core.messages import BaseMessage

from app.core.errors import LLMUnavailableError
from app.llm.base import LLMResult
from app.llm.offline_kb import KB, match_topic

SUPPORTED_TASKS = {"explain", "general", "quiz", "summarize", "summarize_chunk"}

STOPWORDS = set(
    """a about above after again all also am an and any are as at be because been before being below between both but by
    can could did do does doing down during each few for from further had has have having he her here hers him his how i if
    in into is it its itself just me more most my no nor not now of off on once only or other our out over own same she should
    so some such than that the their them then there these they this those through to too under until up very was we were what
    when where which while who whom why will with would you your their which also may many much used using use""".split()
)

OFFLINE_NOTE = (
    "\n\n---\n*Offline fallback: no language model is connected, so this answer came from StudyMate's small built-in "
    "knowledge base. Start Ollama (`ollama serve` + `ollama pull <model>`) for full answers.*"
)


class OfflineProvider:
    name = "offline"
    model = "built-in-knowledge-base"
    is_offline = True

    def supports(self, task: str) -> bool:
        return task in SUPPORTED_TASKS

    def status(self) -> dict[str, Any]:
        return {"provider": self.name, "model": self.model, "reachable": True, "model_available": True,
                "hint": "Offline fallback is active. Configure Ollama for real model answers."}

    def invoke(
        self,
        messages: list[BaseMessage],
        *,
        task: str = "chat",
        json_mode: bool = False,
        temperature: float | None = None,
        hints: dict[str, Any] | None = None,
    ) -> LLMResult:
        hints = hints or {}
        started = time.perf_counter()
        if task == "explain":
            text = self._explain(hints)
        elif task in ("general", "chat"):
            text = self._general(hints)
        elif task == "quiz":
            text = self._quiz(hints)
        elif task == "summarize":
            text = self._summarize(hints)
        elif task == "summarize_chunk":
            text = self._summarize_chunk(hints)
        else:
            raise LLMUnavailableError(
                f"The offline fallback cannot perform the '{task}' task.",
                hint="Start Ollama to enable this capability.",
            )
        return LLMResult(
            text=text,
            provider=self.name,
            model=self.model,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    # ------------------------------------------------------------------ explain
    def _explain(self, hints: dict[str, Any]) -> str:
        query = str(hints.get("query", ""))
        style = (hints.get("style") or "").lower()
        language = (hints.get("language") or "").lower()
        prefs = [p.lower() for p in hints.get("learning_preferences") or []]
        key = match_topic(query)
        if key is None:
            topics = ", ".join(e["title"] for e in KB.values())
            return (
                f"I can't answer that without a language model. No LLM is reachable right now, and the offline "
                f"fallback only covers: {topics}.\n\nStart Ollama (`ollama serve`, then `ollama pull llama3.2`) "
                f"and ask again for a full answer."
            )
        e = KB[key]
        concise = "concise" in style or "simple" in style
        parts = [f"## {e['title']}", e["definition"]]
        if "analog" in style or "real-world" in style:
            parts += ["### Real-world analogy", e["analogy"]]
        if not concise or any("step" in p for p in prefs):
            parts += ["### How it works", "\n".join(f"{i}. {s}" for i, s in enumerate(e["steps"], 1))]
        parts += ["### Key points", "\n".join(f"- {p}" for p in e["key_points"])]
        want_code = bool(language) or any("code" in p for p in prefs) or "code" in style
        if want_code and e.get("code"):
            code = e["code"]
            lang = language if language in code else next(iter(code))
            note = "" if (not language or language == lang) else f"\n\n*(No {language} sample is built in; showing {lang}.)*"
            parts += [f"### Code example ({lang})", f"```{lang}\n{code[lang]}\n```{note}"]
        return "\n\n".join(parts) + OFFLINE_NOTE

    def _general(self, hints: dict[str, Any]) -> str:
        if hints.get("intent") == "preference":
            saved = hints.get("detected_preferences") or []
            if saved:
                bullets = "\n".join(f"- {s}" for s in saved)
                return (
                    "Got it - I'll remember that and tailor future explanations to it, in every conversation:\n\n"
                    f"{bullets}\n\nYou can review or remove it any time in the Memory Inspector."
                )
            return (
                "Thanks for telling me. I couldn't pin that down to a specific preference I can save "
                "(for example an explanation style, a programming language or your current subjects). "
                "Try: \"I prefer explanations using real-world analogies.\""
            )
        return (
            "Hi! I'm StudyMate. Ask me to **explain** a concept, **quiz** you on a topic, or **summarize** your notes "
            "(paste them in the message or use the Notes Summarizer)."
        )

    # --------------------------------------------------------------------- quiz
    def _quiz(self, hints: dict[str, Any]) -> str:
        topic = str(hints.get("topic", ""))
        n = max(1, int(hints.get("n", 5)))
        difficulty = str(hints.get("difficulty", "medium")).lower()
        key = match_topic(topic)
        if key is None:
            titles = ", ".join(e["title"] for e in KB.values())
            raise LLMUnavailableError(
                f"No language model is reachable, and the offline fallback has no quiz material for '{topic}'.",
                hint=f"Start Ollama for any topic, or try one of: {titles}.",
            )
        entry = KB[key]
        pool = sorted(entry["quiz"], key=lambda q: (q["d"] != difficulty, q["d"]))
        questions = []
        for item in pool[:n]:
            options = [item["correct"], *item["wrong"]]
            options.sort(key=lambda o: hashlib.sha1((item["q"] + o).encode()).hexdigest())
            questions.append(
                {
                    "question": item["q"],
                    "options": options,
                    "answer_index": options.index(item["correct"]),
                    "explanation": item["why"],
                }
            )
        return json.dumps({"topic": entry["title"], "questions": questions})

    # ---------------------------------------------------------------- summarize
    @staticmethod
    def _sentences(text: str) -> list[str]:
        parts = re.split(r"(?<=[.!?])\s+|\n+", text)
        return [p.strip(" -*#\t") for p in parts if len(p.strip()) > 25]

    @staticmethod
    def _tokens(sentence: str) -> list[str]:
        return [w for w in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", sentence.lower()) if w not in STOPWORDS]

    def _rank(self, text: str, k: int) -> list[str]:
        sents = self._sentences(text)
        if not sents:
            return []
        freq = Counter(w for s in sents for w in self._tokens(s))
        scored = []
        for i, s in enumerate(sents):
            toks = self._tokens(s)
            score = sum(freq[w] for w in toks) / (max(len(toks), 1) ** 0.6)
            scored.append((score, i, s))
        top = sorted(scored, reverse=True)[:k]
        return [s for _, _, s in sorted(top, key=lambda t: t[1])]

    def _summarize_chunk(self, hints: dict[str, Any]) -> str:
        return "\n".join(f"- {s[:240]}" for s in self._rank(str(hints.get("text", "")), 5))

    def _summarize(self, hints: dict[str, Any]) -> str:
        text = str(hints.get("text", ""))
        length = hints.get("length", "medium")
        n_summary = {"short": 2, "medium": 4, "detailed": 7}.get(length, 4)
        sents = self._sentences(text)
        freq = Counter(w for s in sents for w in self._tokens(s))
        phrases = Counter(re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", text))
        concepts: list[str] = [p for p, _ in phrases.most_common(4)]
        for w, _ in freq.most_common(20):
            if len(concepts) >= 8:
                break
            if not any(w in c.lower() for c in concepts):
                concepts.append(w.capitalize())
        ranked = self._rank(text, n_summary + 6)
        summary_sents = ranked[:n_summary]
        notes = [s[:180] for s in ranked[n_summary:]] or [s[:180] for s in ranked]
        terms = []
        for c in concepts[:6]:
            definition = next((s for s in sents if c.lower() in s.lower()), "")
            if definition:
                terms.append({"term": c, "definition": definition[:220]})
        first = text.strip().splitlines()[0].strip(" #") if text.strip() else "Notes"
        title = first if 3 < len(first) <= 70 else " ".join(first.split()[:7])
        return json.dumps(
            {
                "title": title,
                "summary": " ".join(summary_sents) or text[:400],
                "key_concepts": concepts[:8],
                "revision_notes": notes[:6],
                "key_terms": terms,
            }
        )
