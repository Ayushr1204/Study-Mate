"""LangGraph construction, conditional routing and reducers."""

from __future__ import annotations

import pytest

from app.graph.builder import NODE_INFO, REDUCERS, ROUTE_MAP, describe_graph, route_by_intent
from app.graph.nodes import NODE_NAMES
from app.graph.state import make_insight, merge_execution_metadata, merge_insights
from tests.conftest import chat


def test_graph_compiles_with_all_expected_nodes(runtime):
    desc = describe_graph(runtime.graph)
    ids = {n["id"] for n in desc["nodes"]}
    assert ids == {"__start__", "__end__", *NODE_NAMES}
    assert set(NODE_INFO) == set(NODE_NAMES), "every real node must be documented, and nothing invented"
    for required in ("load_memory_node", "router_node", "explanation_node", "quiz_node",
                     "summarization_node", "response_node", "memory_update_node"):
        assert required in ids


def test_conditional_edges_come_from_router_and_cover_every_intent(runtime):
    desc = describe_graph(runtime.graph)
    conditional = [e for e in desc["edges"] if e["conditional"]]
    assert {e["source"] for e in conditional} == {"router_node"}
    assert {e["target"] for e in conditional} == set(ROUTE_MAP.values())
    normal = {(e["source"], e["target"]) for e in desc["edges"] if not e["conditional"]}
    assert ("__start__", "load_memory_node") in normal
    assert ("load_memory_node", "router_node") in normal
    assert ("response_node", "memory_update_node") in normal
    assert ("memory_update_node", "__end__") in normal
    assert "router_node" in desc["mermaid"] and "-. " in desc["mermaid"]  # dotted edge = conditional in Mermaid


def test_route_function_falls_back_to_explanation():
    assert route_by_intent({"intent": "quiz"}) == "quiz"
    assert route_by_intent({"intent": "nonsense"}) == "explanation"
    assert route_by_intent({}) == "explanation"


@pytest.mark.parametrize(
    "message, intent, processing_node",
    [
        ("Explain how TCP handshakes work", "explanation", "explanation_node"),
        ("Quiz me on photosynthesis with 3 questions", "quiz", "quiz_node"),
        ("Summarize this:\n" + "Mitochondria produce ATP through oxidative phosphorylation. " * 5, "summarization", "summarization_node"),
        ("I prefer step-by-step explanations.", "preference", "general_node"),
        ("hello", "general", "general_node"),
    ],
)
def test_router_selects_correct_node_for_each_intent(client, message, intent, processing_node):
    body = chat(client, message)
    ex = body["execution"]
    assert ex["intent"] == intent
    assert ex["path"] == ["load_memory_node", "router_node", processing_node, "response_node", "memory_update_node"]
    other_processing = {"explanation_node", "quiz_node", "summarization_node", "general_node"} - {processing_node}
    assert not other_processing & set(ex["path"])


def test_router_uses_llm_classifier_when_rules_are_inconclusive(client, llm):
    llm.classify_as = "general"
    body = chat(client, "photosynthesis chloroplast")  # no rule matches
    assert body["execution"]["route"]["method"] == "llm"
    assert body["execution"]["intent"] == "general"
    assert llm.calls_for("classify")


def test_router_defaults_to_explanation_if_classifier_output_is_invalid(client, llm):
    llm.classify_as = "something-else"
    body = chat(client, "photosynthesis chloroplast")
    assert body["execution"]["route"]["method"] == "default"
    assert body["execution"]["intent"] == "explanation"


def test_chat_quiz_request_extracts_parameters(client, llm):
    chat(client, "Give me a hard quiz on binary trees with 4 questions")
    call = llm.calls_for("quiz")[0]
    assert call.hints == {"topic": "binary trees", "n": 4, "difficulty": "hard"}


# ------------------------------------------------------------------ reducers
def test_merge_insights_accumulates_instead_of_replacing():
    a = make_insight("topic", "Deadlock", "explanation")
    b = make_insight("topic", "deadlock", "quiz")
    c = make_insight("topic", "Paging", "explanation")
    merged = merge_insights([a], [b, c])
    assert len(merged) == 2
    deadlock = next(i for i in merged if i["topic"].lower() == "deadlock")
    assert deadlock["count"] == 2
    assert deadlock["intents"] == ["explanation", "quiz"]
    assert a["count"] == 1, "inputs must not be mutated"
    assert merge_insights(None, None) == []


def test_merge_execution_metadata_appends_and_resets():
    first = merge_execution_metadata({}, {"_reset": True, "run_id": "1", "trace": [{"node": "a"}]})
    second = merge_execution_metadata(first, {"trace": [{"node": "b"}], "memory_changes": [1]})
    assert [t["node"] for t in second["trace"]] == ["a", "b"] and second["memory_changes"] == [1]
    fresh = merge_execution_metadata(second, {"_reset": True, "run_id": "2", "trace": [{"node": "x"}]})
    assert [t["node"] for t in fresh["trace"]] == ["x"] and "memory_changes" not in fresh


def test_reducers_work_through_the_real_graph_across_turns(client, runtime):
    t = client.post("/api/threads").json()["id"]
    for text in ["Explain deadlock", "Explain deadlock again", "Explain paging"]:
        chat(client, text, t)
    values = runtime.graph.get_state({"configurable": {"thread_id": t}}).values
    # add_messages: 3 human + 3 AI, nothing dropped or replaced
    assert [m.type for m in values["messages"]] == ["human", "ai"] * 3
    assert len({m.id for m in values["messages"]}) == 6
    # merge_insights: "deadlock" seen twice (the "again" suffix is normalised away)
    insights = {i["topic"]: i for i in values["learning_insights"]}
    assert insights["deadlock"]["count"] == 2
    assert insights["paging"]["count"] == 1
    # execution_metadata is reset every run: the trace only holds the latest run (5 nodes), not 15
    assert len(values["execution_metadata"]["trace"]) == 5


def test_reducer_documentation_matches_state_annotations(runtime):
    desc = describe_graph(runtime.graph)
    assert set(desc["reducers"]) == set(REDUCERS) == {"messages", "learning_insights", "execution_metadata"}
    for field in REDUCERS:
        assert field in desc["state_fields"]
    for required in ("messages", "user_id", "thread_id", "intent", "current_query", "student_profile",
                     "learning_insights", "generated_content", "context_statistics", "execution_metadata"):
        assert required in desc["state_fields"]


def test_node_trace_entries_are_real_measurements(client):
    ex = chat(client, "Explain recursion")["execution"]
    assert [t["node"] for t in ex["trace"]] == ex["path"]
    assert all(t["status"] == "ok" and isinstance(t["duration_ms"], int) and t["started_at"] for t in ex["trace"])
    assert ex["trace"][1]["detail"]["method"] == "rules"
