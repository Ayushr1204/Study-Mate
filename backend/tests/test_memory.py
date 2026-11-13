"""Long-term memory: extraction, Store persistence, cross-thread retrieval, isolation."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.memory.extraction import extract_rules, validate_llm_extraction
from app.memory.profile import ProfileManager, ProfileUpdates
from tests.conftest import ScriptedLLM, chat, make_settings


# ------------------------------------------------------------------ extraction
@pytest.mark.parametrize(
    "text, style, language, subjects, prefs",
    [
        ("I prefer explanations using real-world analogies.", "real-world analogies", None, [], []),
        ("Please always explain things with analogies", "real-world analogies", None, [], []),
        ("I like step-by-step explanations", None, None, [], ["step-by-step explanations"]),
        ("I prefer simple language and diagrams.", "simple language", None, [], ["visual diagrams"]),
        ("I mostly code in Python.", None, "Python", [], []),
        ("My favorite programming language is C++", None, "C++", [], []),
        ("Show me examples in Java please", None, "Java", [], []),
        ("I'm currently studying Operating Systems, DBMS and computer networks this semester.", None, None,
         ["Operating Systems", "DBMS", "Computer Networks"], []),
    ],
)
def test_rule_extraction_finds_structured_facts(text, style, language, subjects, prefs):
    u = extract_rules(text)
    assert (u.style, u.language, u.subjects, u.learning_preferences) == (style, language, subjects, prefs)


@pytest.mark.parametrize("text", [
    "Explain CPU scheduling.", "What is a deadlock?", "I don't like analogies.", "I hate step-by-step guides",
    "The python ate the mouse", "How do I go about learning go?", "I prefer real numbers over complex ones",
])
def test_extraction_ignores_questions_negations_and_noise(text):
    assert extract_rules(text).is_empty()


def test_llm_extraction_output_is_validated_against_allow_list():
    raw = json.dumps({"preferred_explanation_style": "visual", "preferred_programming_language": "Cobol-ish",
                      "current_subjects": ["Math", 5, "x" * 90], "learning_preferences": "not a list",
                      "password": "hunter2", "ssn": "123"})
    u = validate_llm_extraction(raw)
    assert u.style == "visual" and u.language is None and u.subjects == ["Math"] and u.learning_preferences == []
    assert validate_llm_extraction("not json at all").is_empty()


# -------------------------------------------------------------------- store
def test_profile_manager_roundtrip_and_namespaces(runtime):
    pm = ProfileManager(runtime.store)
    assert pm.inspect("alice")["found"] is False
    profile, changes = pm.apply_updates("alice", ProfileUpdates(style="analogies", language="Python", subjects=["OS", "OS", "DBMS"]))
    assert [c["field"] for c in changes] == ["preferred_explanation_style", "preferred_programming_language", "current_subjects", "current_subjects"]
    assert profile.current_subjects == ["OS", "DBMS"]
    _, again = pm.apply_updates("alice", ProfileUpdates(style="analogies"))
    assert again == [], "re-applying an identical fact is not a change"
    info = pm.inspect("alice")
    assert info["namespace"] == ["users", "alice", "profile"] and info["found"] and info["created_at"]
    assert pm.inspect("bob")["found"] is False and pm.get("bob").is_empty()


def test_preference_taught_in_thread_a_is_used_in_thread_b(client, llm):
    """The mandatory acceptance test from the assignment."""
    a = client.post("/api/threads").json()["id"]
    first = chat(client, "I prefer explanations using real-world analogies.", a)
    assert first["execution"]["intent"] == "preference"
    assert first["execution"]["memory_changes"] == [
        {"field": "preferred_explanation_style", "action": "set", "old": None, "new": "real-world analogies"}]
    assert client.get("/api/memory").json()["profile"]["preferred_explanation_style"] == "real-world analogies"

    b = client.post("/api/threads").json()["id"]
    second = chat(client, "Explain CPU scheduling.", b)
    ex = second["execution"]
    assert ex["retrieved_memory"]["found"] and ex["retrieved_memory"]["fields"] == ["preferred_explanation_style"]
    assert ex["retrieved_memory"]["namespace"] == ["users", "demo-student", "profile"]
    call = llm.calls_for("explain")[-1]
    assert "real-world analogies" in call.system, "retrieved memory must reach the model prompt"
    assert call.hints["style"] == "real-world analogies"
    assert "real-world analogies" in second["message"]["content"]
    # B never saw A's messages
    assert all("prefer" not in str(m.content) for m in call.history)


def test_offline_fallback_answer_actually_uses_the_analogy(tmp_path):
    """End-to-end without any LLM: the built-in provider honours the retrieved preference."""
    with TestClient(create_app(make_settings(tmp_path))) as c:
        before = chat(c, "Explain CPU scheduling.")["message"]["content"]
        chat(c, "I prefer explanations using real-world analogies.")
        t2 = c.post("/api/threads").json()["id"]
        after = chat(c, "Explain CPU scheduling.", t2)["message"]["content"]
    assert "analogy" not in before.lower() and "supermarket" not in before.lower()
    assert "Real-world analogy" in after and "supermarket" in after


def test_memory_survives_restart(tmp_path):
    settings = make_settings(tmp_path)
    with TestClient(create_app(settings, ScriptedLLM())) as c1:
        chat(c1, "I prefer explanations using real-world analogies. I mostly code in Python.")
    llm2 = ScriptedLLM()
    with TestClient(create_app(settings, llm2)) as c2:
        p = c2.get("/api/memory").json()["profile"]
        assert p["preferred_explanation_style"] == "real-world analogies" and p["preferred_programming_language"] == "Python"
        chat(c2, "Explain recursion")
        assert "real-world analogies" in llm2.calls_for("explain")[0].system


def test_users_have_isolated_memory_namespaces(client, llm):
    chat(client, "I prefer explanations using real-world analogies.", user="alice")
    chat(client, "I prefer concise answers.", user="bob")
    assert client.get("/api/memory", headers={"X-User-Id": "alice"}).json()["profile"]["preferred_explanation_style"] == "real-world analogies"
    assert client.get("/api/memory", headers={"X-User-Id": "bob"}).json()["profile"]["preferred_explanation_style"] == "concise"
    assert client.get("/api/memory", headers={"X-User-Id": "carol"}).json()["found"] is False
    chat(client, "Explain recursion", user="carol")
    assert "real-world analogies" not in llm.calls_for("explain")[-1].system
    assert client.get("/api/memory").json()["found"] is False  # default user untouched
    # deleting alice's memory leaves bob's alone
    assert client.delete("/api/memory", headers={"X-User-Id": "alice"}).status_code == 204
    assert client.get("/api/memory", headers={"X-User-Id": "bob"}).json()["found"] is True


def test_memory_management_endpoints(client):
    chat(client, "I'm studying Operating Systems and DBMS. I mostly code in Python.")
    m = client.get("/api/memory").json()["profile"]
    assert m["current_subjects"] == ["Operating Systems", "DBMS"]

    patched = client.patch("/api/memory", json={"preferred_explanation_style": "visual diagrams", "learning_preferences": ["practice problems"]}).json()
    assert patched["profile"]["preferred_explanation_style"] == "visual diagrams"
    assert patched["profile"]["learning_preferences"] == ["practice problems"]
    assert patched["profile"]["current_subjects"] == ["Operating Systems", "DBMS"], "untouched fields stay"

    removed = client.delete("/api/memory/current_subjects", params={"value": "dbms"}).json()["profile"]
    assert removed["current_subjects"] == ["Operating Systems"]
    assert client.delete("/api/memory/preferred_programming_language").json()["profile"]["preferred_programming_language"] is None
    assert client.delete("/api/memory/not_a_field").status_code == 404
    assert client.patch("/api/memory", json={"preferred_explanation_style": "x" * 200}).status_code == 422

    assert client.delete("/api/memory").status_code == 204
    cleared = client.get("/api/memory").json()
    assert cleared["found"] is False and cleared["profile"]["current_subjects"] == []


def test_conversation_content_is_never_stored_as_memory(client, runtime):
    secret = "my cat Mr Whiskers has a birthday on 3 March and my phone is 5551234"
    chat(client, f"Explain recursion. By the way {secret}")
    chat(client, "I prefer explanations using real-world analogies.")
    stored = json.dumps(runtime.profiles.inspect("demo-student")["profile"])
    assert "Whiskers" not in stored and "5551234" not in stored
    assert set(json.loads(stored)) == {"preferred_explanation_style", "preferred_programming_language", "current_subjects",
                                       "learning_preferences", "topics_studied", "revision_areas", "updated_at"}


def test_pasted_notes_and_tool_requests_never_teach_the_profile(client):
    notes = "I prefer to skip lunch. I like analogies in poems. Mitochondria make ATP through respiration in cells. " * 3
    chat(client, "Summarize this:\n" + notes)
    client.post("/api/summarize", json={"text": notes})
    assert client.get("/api/memory").json()["profile"]["preferred_explanation_style"] is None


def test_hybrid_extraction_uses_llm_only_when_rules_find_nothing(tmp_path):
    llm = ScriptedLLM(extract_json=json.dumps({"preferred_explanation_style": "storytelling", "current_subjects": [],
                                                "preferred_programming_language": None, "learning_preferences": []}))
    with TestClient(create_app(make_settings(tmp_path, memory_extraction="hybrid"), llm)) as c:
        chat(c, "Stories really help me learn, I like when you teach through them")
        assert c.get("/api/memory").json()["profile"]["preferred_explanation_style"] == "storytelling"
        assert len(llm.calls_for("extract")) == 1
        chat(c, "I prefer concise answers.")  # rules succeed -> no further LLM extraction call
        assert len(llm.calls_for("extract")) == 1


def test_topics_studied_are_recorded_as_structured_facts(client):
    chat(client, "Explain deadlock")
    chat(client, "Explain deadlock once more")
    topics = client.get("/api/memory").json()["profile"]["topics_studied"]
    assert [(t["topic"], t["count"]) for t in topics] == [("deadlock", 2)]
