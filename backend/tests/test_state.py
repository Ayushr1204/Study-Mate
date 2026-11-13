"""Checkpointing, thread isolation, persistence across restarts."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import ScriptedLLM, chat, make_settings


def test_each_conversation_has_independent_history(client):
    a = client.post("/api/threads").json()["id"]
    b = client.post("/api/threads").json()["id"]
    chat(client, "Explain deadlock", a)
    chat(client, "Explain deadlock in detail", a)
    chat(client, "Explain recursion", b)

    msgs_a = client.get(f"/api/threads/{a}").json()["messages"]
    msgs_b = client.get(f"/api/threads/{b}").json()["messages"]
    assert len(msgs_a) == 4 and len(msgs_b) == 2
    assert all("recursion" not in m["content"].lower() for m in msgs_a)
    assert all("deadlock" not in m["content"].lower() for m in msgs_b)
    assert {m["id"] for m in msgs_a}.isdisjoint({m["id"] for m in msgs_b})


def test_switching_threads_restores_the_right_history(client):
    a = client.post("/api/threads").json()["id"]
    b = client.post("/api/threads").json()["id"]
    chat(client, "Explain paging", a)
    chat(client, "Explain binary search", b)
    chat(client, "Explain TLB", a)  # back to A after B
    assert [m["role"] for m in client.get(f"/api/threads/{a}").json()["messages"]] == ["user", "assistant"] * 2
    assert client.get(f"/api/threads/{b}").json()["messages"][0]["content"] == "Explain binary search"


def test_follow_up_sees_earlier_turns_of_same_thread_only(client, llm):
    a = client.post("/api/threads").json()["id"]
    b = client.post("/api/threads").json()["id"]
    chat(client, "Explain deadlock", a)
    chat(client, "Explain recursion", b)
    chat(client, "Give an example", a)
    history = [str(m.content) for m in llm.calls_for("explain")[-1].history]
    assert "Explain deadlock" in history and "Give an example" in history
    assert not any("recursion" in h.lower() and h.startswith("Explain recursion") for h in history)


def test_checkpoints_are_written_per_step(client):
    t = client.post("/api/threads").json()["id"]
    chat(client, "Explain paging", t)
    first = client.get(f"/api/threads/{t}/state").json()
    chat(client, "Explain TLB", t)
    second = client.get(f"/api/threads/{t}/state").json()
    assert second["checkpoint_id"] != first["checkpoint_id"]
    assert len(second["checkpoints"]) > len(first["checkpoints"]) >= 6
    assert second["storage"]["checkpointer"] == "SqliteSaver"
    # message_count per checkpoint is non-decreasing over time (history is cumulative)
    counts = [c["message_count"] for c in reversed(second["checkpoints"])]
    assert counts == sorted(counts) and counts[-1] == 4


def test_persists_across_backend_restart(tmp_path):
    settings = make_settings(tmp_path)
    with TestClient(create_app(settings, ScriptedLLM())) as c1:
        t = c1.post("/api/threads").json()["id"]
        chat(c1, "Explain paging", t)
        chat(c1, "I prefer explanations using real-world analogies.", t)
        before = c1.get(f"/api/threads/{t}").json()
        assert len(before["messages"]) == 4

    with TestClient(create_app(settings, ScriptedLLM())) as c2:  # brand-new runtime, same files
        after = c2.get(f"/api/threads/{t}").json()
        assert [m["content"] for m in after["messages"]] == [m["content"] for m in before["messages"]]
        assert [x["id"] for x in c2.get("/api/threads").json()] == [t]
        chat(c2, "Explain TLB", t)  # and the thread keeps working
        assert len(c2.get(f"/api/threads/{t}").json()["messages"]) == 6
        assert c2.get("/api/memory").json()["profile"]["preferred_explanation_style"] == "real-world analogies"


def test_delete_thread_removes_checkpoints(client, runtime):
    t = client.post("/api/threads").json()["id"]
    chat(client, "Explain paging", t)
    assert client.delete(f"/api/threads/{t}").status_code == 204
    assert client.get(f"/api/threads/{t}").status_code == 404
    assert runtime.graph.get_state({"configurable": {"thread_id": t}}).values == {}
    assert client.delete(f"/api/threads/{t}").status_code == 404


def test_rename_thread_and_auto_title(client):
    t = client.post("/api/threads").json()
    assert t["title"] == "New conversation"
    body = chat(client, "Explain CPU scheduling", t["id"])
    assert body["title"] == "Explain CPU scheduling"
    renamed = client.patch(f"/api/threads/{t['id']}", json={"title": "  OS   notes "}).json()
    assert renamed["title"] == "OS notes"
    assert client.patch(f"/api/threads/{t['id']}", json={"title": "   "}).status_code == 422
    chat(client, "Explain paging", t["id"])
    assert client.get(f"/api/threads/{t['id']}").json()["title"] == "OS notes"  # auto-title never overwrites a name


def test_other_users_cannot_access_a_thread(client):
    t = client.post("/api/threads", headers={"X-User-Id": "alice"}).json()["id"]
    chat(client, "Explain paging", t, user="alice")
    assert client.get(f"/api/threads/{t}", headers={"X-User-Id": "bob"}).status_code == 404
    assert client.get(f"/api/threads/{t}/state", headers={"X-User-Id": "bob"}).status_code == 404
    assert client.delete(f"/api/threads/{t}", headers={"X-User-Id": "bob"}).status_code == 404
    r = client.post("/api/chat", json={"message": "hi", "thread_id": t}, headers={"X-User-Id": "bob"})
    assert r.status_code == 404
    assert client.get("/api/threads", headers={"X-User-Id": "bob"}).json() == []


def test_failed_run_leaves_thread_usable_and_orphan_turn_is_filtered(client, llm):
    t = client.post("/api/threads").json()["id"]
    chat(client, "Explain paging", t)
    from app.core.errors import LLMUnavailableError

    llm.fail_with = LLMUnavailableError("model down", hint="start it")
    r = client.post("/api/chat", json={"message": "Explain TLB", "thread_id": t})
    assert r.status_code == 503 and r.json()["error"]["hint"] == "start it"
    assert r.json()["error"]["node"] == "explanation_node"
    ex = client.get("/api/executions/latest", params={"thread_id": t}).json()["execution"]
    assert ex["status"] == "error" and ex["path"][-1] == "explanation_node"

    llm.fail_with = None
    chat(client, "Explain caching", t)
    sent = [str(m.content) for m in llm.calls_for("explain")[-1].history]
    assert "Explain TLB" not in sent, "the unanswered user turn must not be replayed to the model"
    assert "Explain paging" in sent and "Explain caching" in sent
