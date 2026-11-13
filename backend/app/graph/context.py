"""Context management: build the model's input from the full checkpointed history.

The checkpoint always keeps the COMPLETE conversation. For every LLM call we derive a *separate*,
smaller list that:

1. filters out messages that should never reach the model (empty, errored, unanswered duplicates),
2. truncates oversized individual messages,
3. trims the oldest turns with ``langchain_core.messages.trim_messages`` so that
   system prompt + history fits the token budget, never starting on an assistant reply,
4. always keeps the latest user message,
5. reports exact statistics (and a per-message decision list) from that real computation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, trim_messages

from app.core.tokens import TokenCounter, content_to_text

TRUNCATION_MARKER = "\n\n[... truncated to fit the context budget ...]\n\n"
MIN_MESSAGE_CAP = 32


@dataclass
class ContextResult:
    messages: list[BaseMessage]  # system prompt + retained history, ready for the model
    stats: dict[str, Any]
    decisions: list[dict[str, Any]]


def role_of(m: BaseMessage) -> str:
    if isinstance(m, HumanMessage):
        return "user"
    if isinstance(m, AIMessage):
        return "assistant"
    if isinstance(m, SystemMessage):
        return "system"
    return m.type


def truncate_to_tokens(text: str, max_tokens: int, counter: TokenCounter) -> str:
    """Keep the head (70%) and tail (30%) of a long text so that it fits max_tokens."""
    if counter.count_text(text) <= max_tokens:
        return text

    def build(n: int) -> str:
        head = int(n * 0.7)
        tail = n - head
        return text[:head] + TRUNCATION_MARKER + (text[-tail:] if tail else "")

    lo, hi = 0, min(len(text), max(max_tokens, 1) * 8)  # a token is never worth more than ~8 chars
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if counter.count_text(build(mid)) <= max_tokens:
            lo = mid
        else:
            hi = mid - 1
    return build(lo)


def _count_list(counter: TokenCounter):
    def count(messages: list[BaseMessage]) -> int:  # first-arg annotation != BaseMessage => list counter
        return counter.count_messages(list(messages))

    return count


def build_context(
    messages: list[BaseMessage],
    system_prompt: str,
    *,
    budget: int,
    max_message_tokens: int,
    counter: TokenCounter,
) -> ContextResult:
    system_msg = SystemMessage(content=system_prompt)
    sys_tokens = counter.count_message(system_msg)
    original_tokens = [counter.count_message(m) for m in messages]
    tokens_before = sys_tokens + sum(original_tokens)
    last = len(messages) - 1

    statuses: list[str | None] = [None] * len(messages)
    for i, m in enumerate(messages):
        text = content_to_text(m.content).strip()
        if isinstance(m, SystemMessage):
            statuses[i] = "filtered_system"  # the system prompt is rebuilt per call, never replayed
        elif not text:
            statuses[i] = "filtered_empty"
        elif isinstance(m, AIMessage) and m.additional_kwargs.get("error"):
            statuses[i] = "filtered_error"
        elif isinstance(m, HumanMessage) and i < last and isinstance(messages[i + 1], HumanMessage):
            statuses[i] = "filtered_unanswered"  # a user turn that never got a reply (e.g. the LLM was down)

    available = max(budget - sys_tokens, 0)
    per_message_cap = max(MIN_MESSAGE_CAP, min(max_message_tokens, available))

    working: list[BaseMessage] = []
    work_index: list[int] = []
    truncated_flags: dict[int, bool] = {}
    effective_tokens: dict[int, int] = {}
    for i, m in enumerate(messages):
        if statuses[i]:
            continue
        copy = m
        if original_tokens[i] > per_message_cap:
            body = truncate_to_tokens(content_to_text(m.content), max(per_message_cap - 4, 1), counter)
            copy = m.model_copy(update={"content": body})
            truncated_flags[i] = True
        working.append(copy)
        work_index.append(i)
        effective_tokens[i] = counter.count_message(copy)

    kept: list[BaseMessage] = []
    if working:
        kept = trim_messages(
            working,
            max_tokens=available,
            token_counter=_count_list(counter),
            strategy="last",
            start_on="human",
            end_on="human",
            include_system=False,
            allow_partial=False,
        )
        if not kept or kept[-1] is not working[-1]:
            # Budget is smaller than even the latest message: never drop the user's current request.
            latest = working[-1]
            if counter.count_message(latest) > available:
                latest = latest.model_copy(
                    update={"content": truncate_to_tokens(content_to_text(latest.content), max(available - 4, MIN_MESSAGE_CAP), counter)}
                )
                truncated_flags[work_index[-1]] = True
                effective_tokens[work_index[-1]] = counter.count_message(latest)
                working[-1] = latest
            kept = [latest]

    kept_ids = {id(m) for m in kept}
    kept_originals = {work_index[j] for j, m in enumerate(working) if id(m) in kept_ids}

    decisions: list[dict[str, Any]] = []
    for i, m in enumerate(messages):
        if statuses[i]:
            status = statuses[i]
        elif i in kept_originals:
            status = "retained"
        else:
            status = "excluded_trimmed"
        text = content_to_text(m.content).replace("\n", " ").strip()
        decisions.append(
            {
                "index": i,
                "id": getattr(m, "id", None),
                "role": role_of(m),
                "status": status,
                "tokens": original_tokens[i],
                "tokens_sent": effective_tokens.get(i, 0) if status == "retained" else 0,
                "truncated": bool(truncated_flags.get(i)) and status == "retained",
                "preview": text[:90],
            }
        )

    tokens_after = sys_tokens + counter.count_messages(kept)
    filtered = sum(1 for d in decisions if d["status"].startswith("filtered"))
    stats = {
        "total_messages": len(messages),
        "retained_messages": len(kept),
        "excluded_messages": len(messages) - len(kept),
        "filtered_messages": filtered,
        "trimmed_messages": sum(1 for d in decisions if d["status"] == "excluded_trimmed"),
        "truncated_messages": sum(1 for d in decisions if d["truncated"]),
        "tokens_before": tokens_before,
        "tokens_after": tokens_after,
        "token_budget": budget,
        "system_prompt_tokens": sys_tokens,
        "max_message_tokens": per_message_cap,
        "token_counter": counter.name,
        "token_counter_exact": counter.exact,
        "within_budget": tokens_after <= budget,
        "scope": "conversation",
        # Compact, index-aligned with the checkpointed messages: [status, tokens, tokens_sent, truncated]
        "decisions": [[d["status"], d["tokens"], d["tokens_sent"], int(d["truncated"])] for d in decisions],
    }
    return ContextResult(messages=[system_msg, *kept], stats=stats, decisions=decisions)
