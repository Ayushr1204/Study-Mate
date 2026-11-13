"""LangGraph nodes. Each has one responsibility and reports a trace entry into ``execution_metadata``.

    load_memory_node     read the user's long-term profile from the Store
    router_node          classify intent (forced > rules > LLM > default)
    explanation_node     personalised explanation (trimmed context -> LLM)
    quiz_node            structured MCQ generation
    summarization_node   structured notes / summaries (map-reduce for long material)
    general_node         greetings and acknowledging stated learning preferences
    response_node        turn generated_content into the assistant message (add_messages reducer)
    memory_update_node   extract + persist durable learning facts into the Store
"""

from __future__ import annotations

import contextlib
import functools
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.store.base import BaseStore

from app.core.config import Settings
from app.core.errors import StudyMateError
from app.core.tokens import TokenCounter, content_to_text
from app.graph.context import build_context
from app.graph.prompts import BASE_SYSTEM, CLASSIFY_SYSTEM, personalization, quiz_system
from app.graph.render import render_quiz_markdown, render_summary_markdown
from app.graph.routing import SUMMARY_RE, classify_rules, extract_quiz_params, extract_topic
from app.graph.state import INTENTS, StudyState, make_insight, utcnow
from app.llm.base import LLMProvider, LLMResult
from app.memory.extraction import LLM_EXTRACT_SYSTEM, extract_rules, looks_like_preference, validate_llm_extraction
from app.memory.profile import ProfileManager, clean_text
from app.models.content import GeneratedQuiz, normalize_quiz
from app.services.structured import call_json, parse_json_loose
from app.services.summarizer import summarize_document

NODE_NAMES = (
    "load_memory_node",
    "router_node",
    "explanation_node",
    "quiz_node",
    "summarization_node",
    "general_node",
    "response_node",
    "memory_update_node",
)


@dataclass
class GraphDeps:
    settings: Settings
    llm: LLMProvider
    counter: TokenCounter


def traced(name: str) -> Callable:
    """Wrap a node: time it, append a trace entry to execution_metadata, tag failures with the node name."""

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
            t0, started = time.perf_counter(), utcnow()
            try:
                update = fn(*args, **kwargs)
            except Exception as exc:
                with contextlib.suppress(Exception):  # exceptions without __dict__ simply stay untagged
                    exc.studymate_node = name  # type: ignore[attr-defined]
                raise
            detail = update.pop("_detail", {})
            meta = update.pop("_meta", {})
            entry = {
                "node": name,
                "status": "ok",
                "started_at": started,
                "duration_ms": int((time.perf_counter() - t0) * 1000),
                "detail": detail,
            }
            update["execution_metadata"] = {**meta, "trace": [entry]}
            return update

        return wrapper

    return decorator


def _llm_meta(res: LLMResult) -> dict[str, Any]:
    return res.meta()


def _valid_topic(topic: str) -> str:
    topic = clean_text(topic)
    return topic if 3 <= len(topic) <= 60 and len(topic.split()) <= 8 else ""


def _last_human_text(state: StudyState) -> str:
    for m in reversed(state.get("messages", [])):
        if isinstance(m, HumanMessage):
            return content_to_text(m.content).strip()
    return ""


def build_nodes(deps: GraphDeps) -> dict[str, Callable]:
    s, llm, counter = deps.settings, deps.llm, deps.counter

    def budget_of(config: RunnableConfig) -> int:
        override = (config.get("configurable") or {}).get("context_budget")
        return int(override) if override else s.context_token_budget

    def context_for(state: StudyState, config: RunnableConfig, system_prompt: str):
        return build_context(
            list(state.get("messages", [])),
            system_prompt,
            budget=budget_of(config),
            max_message_tokens=s.max_message_tokens,
            counter=counter,
        )

    # ------------------------------------------------------------------ load_memory
    @traced("load_memory_node")
    def load_memory_node(state: StudyState, config: RunnableConfig, *, store: BaseStore) -> dict[str, Any]:
        cfg = config.get("configurable") or {}
        user_id = cfg.get("user_id") or state.get("user_id") or s.default_user_id
        thread_id = cfg.get("thread_id") or state.get("thread_id") or ""
        info = ProfileManager(store).inspect(user_id)
        profile = info["profile"]
        fields = [k for k, v in profile.items() if v and k != "updated_at"]
        return {
            "user_id": user_id,
            "thread_id": thread_id,
            "current_query": _last_human_text(state),
            "student_profile": profile,
            "retrieved_memory": {
                "namespace": info["namespace"],
                "key": info["key"],
                "found": info["found"],
                "fields": fields,
                "updated_at": info["updated_at"],
            },
            "intent": "",
            "topic": "",
            "generated_content": {},
            "context_statistics": {},
            # NB: the config key is "request_id" - LangGraph reserves "run_id" inside `configurable`
            # and a thread silently stops running new inputs if it is set.
            "_meta": {"_reset": True, "run_id": cfg.get("request_id"), "started_at": utcnow(), "user_id": user_id, "thread_id": thread_id},
            "_detail": {"namespace": "/".join(info["namespace"]), "profile_found": info["found"], "fields_loaded": fields},
        }

    # ------------------------------------------------------------------- router
    @traced("router_node")
    def router_node(state: StudyState, config: RunnableConfig) -> dict[str, Any]:
        query = state.get("current_query", "")
        forced = state.get("forced_intent")
        payload = dict(state.get("request_payload") or {})
        reason = ""
        if forced in INTENTS:
            intent, method, reason = forced, "forced", "intent fixed by the calling endpoint"
        else:
            intent, method = "", ""
            if s.router_mode in ("hybrid", "rules"):
                hit = classify_rules(query)
                if hit:
                    (intent, reason), method = hit, "rules"
            if not intent and s.router_mode in ("hybrid", "llm") and not llm.is_offline:
                try:
                    res = llm.invoke(
                        [SystemMessage(content=CLASSIFY_SYSTEM), HumanMessage(content=query[:2000])],
                        task="classify", json_mode=True, temperature=0.0,
                    )
                    candidate = str(parse_json_loose(res.text).get("intent", "")).lower()
                    if candidate in INTENTS:
                        intent, method, reason = candidate, "llm", f"classified by {res.provider}/{res.model}"
                except (StudyMateError, ValueError):
                    pass
            if not intent:
                intent, method, reason = "explanation", "default", "no rule matched; defaulting to explanation"

        topic = ""
        update: dict[str, Any] = {}
        if intent == "explanation":
            topic = _valid_topic(extract_topic(query))
        elif intent == "quiz":
            params = {**extract_quiz_params(query), **{k: v for k, v in payload.items() if v}}
            update["request_payload"] = {**payload, **params}
            topic = _valid_topic(str(params.get("topic", "")))
        update.update(
            intent=intent,
            topic=topic,
            _detail={"intent": intent, "method": method, "reason": reason, "topic": topic or None},
        )
        return update

    # -------------------------------------------------------------- explanation
    @traced("explanation_node")
    def explanation_node(state: StudyState, config: RunnableConfig) -> dict[str, Any]:
        profile = state.get("student_profile") or {}
        system = BASE_SYSTEM + personalization(profile, state.get("learning_insights"))
        ctx = context_for(state, config, system)
        res = llm.invoke(
            ctx.messages,
            task="explain",
            hints={
                "query": state.get("current_query", ""),
                "style": profile.get("preferred_explanation_style"),
                "language": profile.get("preferred_programming_language"),
                "learning_preferences": profile.get("learning_preferences", []),
            },
        )
        topic = state.get("topic", "")
        out: dict[str, Any] = {
            "generated_content": {"type": "explanation", "answer": res.text, "llm": _llm_meta(res)},
            "context_statistics": ctx.stats,
            "_detail": {"personalised_with": [k for k in ("preferred_explanation_style", "preferred_programming_language", "learning_preferences") if profile.get(k)],
                        "llm": f"{res.provider}/{res.model}", "latency_ms": res.latency_ms},
        }
        if topic:
            out["learning_insights"] = [make_insight("topic", topic, "explanation")]
        return out

    # --------------------------------------------------------------------- quiz
    @traced("quiz_node")
    def quiz_node(state: StudyState, config: RunnableConfig) -> dict[str, Any]:
        payload = state.get("request_payload") or {}
        topic_in = str(payload.get("topic") or "general knowledge")
        n = min(max(int(payload.get("n", 5)), 1), 15)
        difficulty = str(payload.get("difficulty", "medium")).lower()
        if difficulty not in ("easy", "medium", "hard"):
            difficulty = "medium"
        profile = state.get("student_profile") or {}
        ctx = context_for(state, config, quiz_system(topic_in, n, difficulty, profile))
        quiz, res, attempts = call_json(
            llm, ctx.messages, GeneratedQuiz, task="quiz", normalize=normalize_quiz,
            hints={"topic": topic_in, "n": n, "difficulty": difficulty},
        )
        questions = [q.model_dump() for q in quiz.questions[:n]]
        warnings = []
        if len(questions) < n:
            warnings.append(f"Only {len(questions)} of the {n} requested questions were available from {res.provider}.")
        title = clean_text(quiz.topic) or clean_text(topic_in)
        content = {"topic": title, "difficulty": difficulty, "requested": n, "questions": questions, "warnings": warnings}
        topic = _valid_topic(title)
        out: dict[str, Any] = {
            "generated_content": {"type": "quiz", "quiz": content, "llm": _llm_meta(res)},
            "context_statistics": ctx.stats,
            "topic": topic,
            "_detail": {"questions": len(questions), "difficulty": difficulty, "attempts": attempts, "llm": f"{res.provider}/{res.model}"},
        }
        if topic:
            out["learning_insights"] = [make_insight("topic", topic, "quiz")]
        return out

    # ------------------------------------------------------------ summarization
    @traced("summarization_node")
    def summarization_node(state: StudyState, config: RunnableConfig) -> dict[str, Any]:
        payload = state.get("request_payload") or {}
        text = str(payload.get("text") or "")
        if not text:
            text = state.get("current_query", "")
            lines = text.splitlines()
            if not state.get("forced_intent") and len(lines) > 1 and SUMMARY_RE.search(lines[0]) and len(lines[0]) < 120:
                text = "\n".join(lines[1:])  # drop the "Summarize this:" command line
        text = text.strip()
        if len(text) < 80:
            return {
                "generated_content": {"type": "explanation", "answer": "Paste the notes you want summarised (at least a few sentences) in your message, "
                                      "or use the **Notes Summarizer** page to upload a TXT, PDF or DOCX file.", "llm": {}},
                "context_statistics": {},
                "_detail": {"skipped": "not enough material to summarise"},
            }
        include = payload.get("include") or ["summary", "concepts", "revision", "terms"]
        length = payload.get("length") or "medium"
        summary, stats, res, info = summarize_document(
            llm, counter, text, include=include, length=length,
            profile=state.get("student_profile") or {}, budget=budget_of(config),
        )
        content = summary.model_dump()
        topic = _valid_topic(summary.title)
        out: dict[str, Any] = {
            "generated_content": {"type": "summary", "summary": content, "processing": info, "llm": _llm_meta(res)},
            "context_statistics": {**stats, "scope": "summarization_prompt", "decisions": [], "processing": info},
            "topic": topic,
            "_detail": {**info, "llm": f"{res.provider}/{res.model}"},
        }
        if topic:
            out["learning_insights"] = [make_insight("topic", topic, "summarization")]
        return out

    # ------------------------------------------------------------------ general
    @traced("general_node")
    def general_node(state: StudyState, config: RunnableConfig) -> dict[str, Any]:
        profile = state.get("student_profile") or {}
        intent = state.get("intent", "general")
        detected = extract_rules(state.get("current_query", "")).describe() if intent == "preference" else []
        system = BASE_SYSTEM + personalization(profile, state.get("learning_insights"))
        if intent == "preference":
            system += (
                "\n\nThe student just told you how they like to learn. Acknowledge it in 2-3 sentences and say how you will "
                "adapt future explanations. Do not explain any topic yet."
            )
            if detected:
                system += " Preferences being saved to long-term memory: " + "; ".join(detected) + "."
        ctx = context_for(state, config, system)
        res = llm.invoke(ctx.messages, task="general", hints={"intent": intent, "detected_preferences": detected, "query": state.get("current_query", "")})
        return {
            "generated_content": {"type": "explanation", "answer": res.text, "llm": _llm_meta(res)},
            "context_statistics": ctx.stats,
            "_detail": {"intent": intent, "preferences_detected": detected, "llm": f"{res.provider}/{res.model}"},
        }

    # ----------------------------------------------------------------- response
    @traced("response_node")
    def response_node(state: StudyState, config: RunnableConfig) -> dict[str, Any]:
        gc = state.get("generated_content") or {}
        kind = gc.get("type", "explanation")
        if kind == "quiz":
            content = render_quiz_markdown(gc["quiz"])
        elif kind == "summary":
            content = render_summary_markdown(gc["summary"])
        else:
            content = gc.get("answer") or "I could not produce an answer."
        meta = state.get("execution_metadata") or {}
        llm_meta = gc.get("llm") or {}
        message = AIMessage(
            content=content,
            additional_kwargs={
                "created_at": utcnow(),
                "intent": state.get("intent"),
                "content_type": kind,
                "provider": llm_meta.get("provider"),
                "model": llm_meta.get("model"),
                "fallback_reason": llm_meta.get("fallback_reason"),
                "run_id": meta.get("run_id"),
                "memory_fields_used": (state.get("retrieved_memory") or {}).get("fields", []),
            },
        )
        return {"messages": [message], "_detail": {"content_type": kind, "chars": len(content)}}

    # ------------------------------------------------------------ memory_update
    @traced("memory_update_node")
    def memory_update_node(state: StudyState, config: RunnableConfig, *, store: BaseStore) -> dict[str, Any]:
        user_id = state.get("user_id") or s.default_user_id
        intent = state.get("intent", "")
        pm = ProfileManager(store)
        query = state.get("current_query", "")
        method = "skipped"
        changes: list[dict[str, Any]] = []
        profile = pm.get(user_id)
        # Only conversational turns may teach the profile. Pasted notes (summarization) and generated
        # quiz requests are arbitrary text and are never mined for preferences.
        if intent in ("explanation", "preference", "general") and not state.get("forced_intent"):
            updates = extract_rules(query)
            method = "rules"
            if s.memory_extraction == "hybrid" and updates.is_empty() and looks_like_preference(query) and not llm.is_offline:
                try:
                    res = llm.invoke([SystemMessage(content=LLM_EXTRACT_SYSTEM), HumanMessage(content=query[:1500])],
                                     task="extract", json_mode=True, temperature=0.0)
                    updates, method = validate_llm_extraction(res.text), "llm"
                except StudyMateError:
                    pass
            profile, changes = pm.apply_updates(user_id, updates)
        topic = state.get("topic", "")
        topic_recorded = None
        if intent in ("explanation", "quiz", "summarization") and topic:
            profile = pm.record_topic(user_id, topic)
            topic_recorded = topic
        insights = [make_insight("preference", f"{c['field']}: {c['new']}", intent or "general") for c in changes]
        out: dict[str, Any] = {
            "student_profile": profile.model_dump(),
            "_meta": {"memory_changes": changes},
            "_detail": {"extraction": method, "changes": changes, "topic_recorded": topic_recorded},
        }
        if insights:
            out["learning_insights"] = insights
        return out

    return {
        "load_memory_node": load_memory_node,
        "router_node": router_node,
        "explanation_node": explanation_node,
        "quiz_node": quiz_node,
        "summarization_node": summarization_node,
        "general_node": general_node,
        "response_node": response_node,
        "memory_update_node": memory_update_node,
    }

