"""Message trimming, filtering and the accuracy of context statistics."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.core.tokens import TokenCounter
from app.graph.context import build_context, truncate_to_tokens
from tests.conftest import chat

counter = TokenCounter("approx")


def conversation(turns: int, words: int = 40) -> list:
    msgs = []
    for i in range(turns):
        msgs.append(HumanMessage(content=f"question {i} " + "word " * words, id=f"h{i}"))
        msgs.append(AIMessage(content=f"answer {i} " + "word " * words, id=f"a{i}"))
    msgs.append(HumanMessage(content="current question", id="current"))
    return msgs


def test_everything_is_kept_when_under_budget():
    msgs = conversation(2)
    ctx = build_context(msgs, "SYSTEM", budget=3000, max_message_tokens=1200, counter=counter)
    assert ctx.stats["retained_messages"] == len(msgs) and ctx.stats["excluded_messages"] == 0
    assert ctx.stats["tokens_before"] == ctx.stats["tokens_after"]
    assert ctx.messages[0].type == "system"


def test_old_messages_are_trimmed_and_budget_respected():
    msgs = conversation(20)
    ctx = build_context(msgs, "SYSTEM PROMPT", budget=400, max_message_tokens=300, counter=counter)
    s = ctx.stats
    assert s["tokens_after"] <= 400 and s["within_budget"]
    assert s["tokens_before"] > 400 > s["tokens_after"]
    assert s["trimmed_messages"] > 0 and s["retained_messages"] + s["excluded_messages"] == s["total_messages"] == len(msgs)
    # newest messages survive, oldest are dropped
    kept_ids = [m.id for m in ctx.messages[1:]]
    assert kept_ids[-1] == "current"
    assert "h0" not in kept_ids and "a0" not in kept_ids
    assert kept_ids == sorted(kept_ids, key=lambda i: [m.id for m in msgs].index(i)), "order preserved"


def test_system_prompt_is_always_first_and_exactly_once():
    ctx = build_context(conversation(10), "KEEP ME", budget=300, max_message_tokens=200, counter=counter)
    systems = [m for m in ctx.messages if isinstance(m, SystemMessage)]
    assert len(systems) == 1 and ctx.messages[0] is systems[0] and systems[0].content == "KEEP ME"


def test_never_starts_with_an_assistant_reply():
    for budget in (250, 300, 350, 420, 500, 700):
        ctx = build_context(conversation(15), "S", budget=budget, max_message_tokens=150, counter=counter)
        assert isinstance(ctx.messages[1], HumanMessage), f"budget={budget}: exchange must start on a user turn"
        assert isinstance(ctx.messages[-1], HumanMessage)


def test_statistics_are_recomputed_exactly():
    msgs = conversation(12)
    ctx = build_context(msgs, "SYSTEM", budget=500, max_message_tokens=250, counter=counter)
    sys_tokens = counter.count_message(SystemMessage(content="SYSTEM"))
    assert ctx.stats["system_prompt_tokens"] == sys_tokens
    assert ctx.stats["tokens_before"] == sys_tokens + sum(counter.count_message(m) for m in msgs)
    assert ctx.stats["tokens_after"] == sum(counter.count_message(m) for m in ctx.messages)
    assert ctx.stats["retained_messages"] == len(ctx.messages) - 1
    statuses = [d["status"] for d in ctx.decisions]
    assert statuses.count("retained") == ctx.stats["retained_messages"]
    assert [d[0] for d in ctx.stats["decisions"]] == statuses


def test_oversized_single_message_is_truncated_not_dropped():
    big = HumanMessage(content="START " + "lorem ipsum " * 2000 + " END", id="big")
    msgs = [big, AIMessage(content="ok", id="a"), HumanMessage(content="what now?", id="cur")]
    ctx = build_context(msgs, "S", budget=800, max_message_tokens=200, counter=counter)
    kept = {m.id: m for m in ctx.messages[1:]}
    assert ctx.stats["truncated_messages"] == 1
    assert counter.count_message(kept["big"]) <= 200
    assert kept["big"].content.startswith("START") and kept["big"].content.endswith("END")
    assert "truncated" in kept["big"].content
    assert msgs[0].content.count("lorem") == 2000, "the original message must not be mutated"


def test_latest_user_message_survives_even_a_tiny_budget():
    msgs = [HumanMessage(content="x " * 3000, id="cur")]
    ctx = build_context(msgs, "S", budget=200, max_message_tokens=1200, counter=counter)
    assert [m.id for m in ctx.messages[1:]] == ["cur"]
    assert ctx.stats["truncated_messages"] == 1 and ctx.stats["tokens_after"] <= 200


def test_filtering_drops_empty_error_and_unanswered_messages():
    msgs = [
        HumanMessage(content="unanswered question", id="u1"),           # followed by another human -> orphan
        HumanMessage(content="real question", id="u2"),
        AIMessage(content="", id="empty"),
        AIMessage(content="boom", id="err", additional_kwargs={"error": True}),
        AIMessage(content="good answer", id="ok"),
        SystemMessage(content="old system", id="sys"),
        HumanMessage(content="current", id="cur"),
    ]
    ctx = build_context(msgs, "S", budget=3000, max_message_tokens=1200, counter=counter)
    by_id = {d["id"]: d["status"] for d in ctx.decisions}
    assert by_id == {"u1": "filtered_unanswered", "u2": "retained", "empty": "filtered_empty", "err": "filtered_error",
                     "ok": "retained", "sys": "filtered_system", "cur": "retained"}
    assert ctx.stats["filtered_messages"] == 4
    assert [m.id for m in ctx.messages[1:]] == ["u2", "ok", "cur"]


def test_truncate_to_tokens_fits_limit():
    text = "alpha beta gamma " * 500
    out = truncate_to_tokens(text, 100, counter)
    assert counter.count_text(out) <= 100
    assert truncate_to_tokens("short", 100, counter) == "short"


# ---------------------------------------------------------------- via the graph
def test_checkpoint_keeps_full_history_while_model_sees_trimmed_context(client, runtime, llm):
    t = client.post("/api/threads").json()["id"]
    filler = "photosynthesis details " * 40
    for i in range(8):
        chat(client, f"Explain topic{i} {filler}", t, context_budget=700)
    stored = runtime.graph.get_state({"configurable": {"thread_id": t}}).values["messages"]
    assert len(stored) == 16, "the checkpoint is never trimmed"
    sent = llm.calls_for("explain")[-1]
    assert len(sent.history) < 15, "the model call was trimmed"
    assert str(sent.history[-1].content).startswith("Explain topic7")
    assert str(sent.history[0].content).startswith("Explain topic")  # starts on a user turn
    assert sent.messages[0].type == "system"


def test_api_reports_real_context_statistics(client):
    t = client.post("/api/threads").json()["id"]
    filler = "word " * 150
    for i in range(6):
        body = chat(client, f"Explain concept {i}. {filler}", t, context_budget=600)
    s = body["execution"]["context"]
    assert s["token_budget"] == 600 and s["tokens_after"] <= 600 < s["tokens_before"]
    assert s["total_messages"] == 11  # 5 earlier turns (10 messages) + the current question
    assert s["retained_messages"] + s["excluded_messages"] == 11
    assert s["scope"] == "conversation" and len(s["decisions"]) == 11
    assert s["token_counter"] == "approx:chars/4"


@pytest.mark.parametrize("bad", [100, 50000, "x"])
def test_invalid_budget_override_is_rejected(client, bad):
    r = client.post("/api/chat", json={"message": "hi", "context_budget": bad})
    assert r.status_code == 422
