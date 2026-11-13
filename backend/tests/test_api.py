"""REST API behaviour: endpoints, validation, errors, quiz / summarizer / upload flows."""

from __future__ import annotations

import io

import pytest
from docx import Document
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app.core.errors import LLMResponseError, LLMUnavailableError
from app.main import create_app
from tests.conftest import ScriptedLLM, chat, make_settings

NOTES = (
    "Photosynthesis converts light energy into chemical energy. Chloroplasts contain chlorophyll which absorbs light. "
    "The light reactions produce ATP and NADPH. The Calvin cycle uses them to fix carbon dioxide into glucose. "
)


def minimal_pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % off for off in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objs) + 1, xref)
    return out


# --------------------------------------------------------------------- basics
def test_health_and_docs(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["token_counter"] == "approx:chars/4"
    assert client.get("/openapi.json").status_code == 200 and client.get("/docs").status_code == 200
    paths = set(client.get("/openapi.json").json()["paths"])
    for p in ["/api/health", "/api/chat", "/api/threads", "/api/threads/{thread_id}", "/api/quiz/generate",
              "/api/quizzes/{quiz_id}/submit", "/api/summarize", "/api/documents/extract", "/api/graph",
              "/api/executions/latest", "/api/memory", "/api/threads/{thread_id}/state", "/api/dashboard"]:
        assert p in paths


def test_graph_endpoint_returns_the_compiled_graph(client):
    g = client.get("/api/graph").json()
    assert any(e["conditional"] for e in g["edges"]) and "flowchart" in g["mermaid"]
    assert next(n for n in g["nodes"] if n["id"] == "router_node")["kind"] == "router"


def test_chat_response_shape_and_timestamps(client):
    body = chat(client, "Explain recursion")
    msg = body["message"]
    assert msg["role"] == "assistant" and msg["created_at"] and msg["meta"]["intent"] == "explanation"
    detail = client.get(f"/api/threads/{body['thread_id']}").json()
    assert detail["messages"][0]["role"] == "user" and detail["messages"][0]["created_at"]
    assert detail["last_execution"]["request_id"] == body["execution"]["request_id"]


@pytest.mark.parametrize("payload", [{}, {"message": ""}, {"message": "   "}, {"message": "x" * 30_001}, {"message": 5}])
def test_chat_rejects_invalid_input(client, payload):
    r = client.post("/api/chat", json=payload)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_unknown_resources_return_404(client):
    assert client.get("/api/threads/nope").status_code == 404
    assert client.post("/api/chat", json={"message": "hi", "thread_id": "nope"}).status_code == 404
    assert client.post("/api/quizzes/nope/submit", json={"answers": []}).status_code == 404
    assert client.get("/api/threads/nope/state").status_code == 404
    assert client.get("/api/nothing-here").status_code == 404


@pytest.mark.parametrize("uid", ["../etc", "a b", "x" * 65, "bad!id"])
def test_invalid_user_id_header_is_rejected(client, uid):
    assert client.get("/api/threads", headers={"X-User-Id": uid}).status_code == 400


def test_llm_unavailable_is_a_clean_503(tmp_path):
    llm = ScriptedLLM(fail_with=LLMUnavailableError("Cannot reach Ollama", hint="ollama serve"))
    with TestClient(create_app(make_settings(tmp_path), llm)) as c:
        r = c.post("/api/chat", json={"message": "Explain paging"})
        assert r.status_code == 503
        assert r.json()["error"] == {"code": "llm_unavailable", "message": "Cannot reach Ollama", "hint": "ollama serve", "node": "explanation_node"}


def test_unexpected_errors_are_reported_without_crashing_the_server(settings, llm):
    with TestClient(create_app(settings, llm), raise_server_exceptions=False) as c:
        llm.fail_with = RuntimeError("kaboom")
        r = c.post("/api/chat", json={"message": "Explain paging"})
        assert r.status_code == 500 and "kaboom" in r.json()["error"]["message"]
        assert r.json()["error"]["node"] == "explanation_node"
        llm.fail_with = None
        assert c.post("/api/chat", json={"message": "Explain paging"}).status_code == 200


def test_fallback_provider_answers_when_primary_is_down(tmp_path, monkeypatch):
    import httpx

    def refuse(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "post", refuse)
    monkeypatch.setattr(httpx, "get", refuse)
    s = make_settings(tmp_path, llm_provider="ollama", llm_fallback="offline")
    with TestClient(create_app(s)) as c:
        body = chat(c, "Explain deadlock")
        assert body["message"]["meta"]["provider"] == "offline" and "refused" not in body["message"]["content"]
        assert "Cannot reach Ollama" in body["message"]["meta"]["fallback_reason"]
        st = c.get("/api/llm/status").json()
        assert st["reachable"] is False and st["active"] == "offline" and "ollama pull" in st["hint"]
    s2 = make_settings(tmp_path / "x", llm_provider="ollama", llm_fallback="none")
    with TestClient(create_app(s2)) as c:
        r = c.post("/api/chat", json={"message": "Explain deadlock"})
        assert r.status_code == 503 and "ollama pull" in r.json()["error"]["hint"]


# ----------------------------------------------------------------------- quiz
def test_quiz_generation_hides_answers_and_scores_server_side(client, llm):
    r = client.post("/api/quiz/generate", json={"topic": "deadlock", "difficulty": "hard", "num_questions": 4})
    assert r.status_code == 200
    quiz = r.json()
    assert len(quiz["questions"]) == 4 and all(set(q) == {"question", "options"} for q in quiz["questions"])
    assert quiz["execution"]["path"][2] == "quiz_node" and quiz["execution"]["route"]["method"] == "forced"
    assert llm.calls_for("quiz")[0].hints == {"topic": "deadlock", "n": 4, "difficulty": "hard"}

    perfect = client.post(f"/api/quizzes/{quiz['quiz_id']}/submit", json={"answers": [0, 1, 2, 3]}).json()
    assert perfect["score"] == 4 and perfect["percent"] == 100 and not perfect["needs_revision"]
    assert perfect["results"][0]["explanation"] and perfect["results"][0]["correct"] == 0

    poor = client.post(f"/api/quizzes/{quiz['quiz_id']}/submit", json={"answers": [3, None, 0, 0]}).json()
    assert poor["score"] == 0 and poor["needs_revision"] and poor["results"][1]["selected"] is None
    assert client.get("/api/memory").json()["profile"]["revision_areas"] == ["Deadlock"]

    client.post(f"/api/quizzes/{quiz['quiz_id']}/submit", json={"answers": [0, 1, 2, 3]})
    assert client.get("/api/memory").json()["profile"]["revision_areas"] == [], "good score clears the revision flag"
    hist = client.get("/api/quizzes").json()
    assert hist[0]["attempts"] == 3 and hist[0]["best_score"] == 4
    assert client.get("/api/dashboard").json()["quiz"]["attempts"] == 3


@pytest.mark.parametrize("body", [
    {"topic": "x"}, {"topic": "ok topic", "num_questions": 0}, {"topic": "ok topic", "num_questions": 99},
    {"topic": "ok topic", "difficulty": "impossible"}, {},
])
def test_quiz_generation_validation(client, body):
    assert client.post("/api/quiz/generate", json=body).status_code == 422


def test_quiz_submission_validation(client):
    q = client.post("/api/quiz/generate", json={"topic": "paging", "num_questions": 2}).json()
    url = f"/api/quizzes/{q['quiz_id']}/submit"
    assert client.post(url, json={"answers": [0]}).status_code == 422
    assert client.post(url, json={"answers": [0, 9]}).status_code == 422
    assert client.post(url, json={"answers": ["a", "b"]}).status_code == 422
    assert client.post(url, json={"answers": [0, 1]}, headers={"X-User-Id": "other"}).status_code == 404


def test_quiz_with_invalid_model_json_retries_then_fails_cleanly(tmp_path):
    class BadQuiz(ScriptedLLM):
        def invoke(self, messages, **kw):
            res = super().invoke(messages, **kw)
            if kw.get("task") == "quiz":
                res.text = "Sure! Here is your quiz: not json"
            return res

    llm = BadQuiz()
    with TestClient(create_app(make_settings(tmp_path), llm)) as c:
        r = c.post("/api/quiz/generate", json={"topic": "paging"})
        assert r.status_code == 502 and r.json()["error"]["code"] == "llm_bad_response"
        assert len(llm.calls_for("quiz")) == 2, "one corrective retry"
        assert "invalid" in str(llm.calls_for("quiz")[1].messages[-1].content)


def test_quiz_json_quirks_are_normalised(tmp_path):
    class Quirky(ScriptedLLM):
        def invoke(self, messages, **kw):
            res = super().invoke(messages, **kw)
            if kw.get("task") == "quiz":
                res.text = '```json\n{"questions":[{"question":"What is 2+2?","choices":["3","4","5","6"],"answer":"B","explanation":"math"},' \
                           '{"question":"Capital of France?","options":["Paris","Rome","Oslo","Bern"],"correct_answer":"Paris"}]}\n```'
            return res

    with TestClient(create_app(make_settings(tmp_path), Quirky())) as c:
        q = c.post("/api/quiz/generate", json={"topic": "misc", "num_questions": 2}).json()
        r = c.post(f"/api/quizzes/{q['quiz_id']}/submit", json={"answers": [1, 0]}).json()
        assert r["score"] == 2


# ----------------------------------------------------------------- summarizer
def test_summarize_endpoint_runs_summarization_node(client, llm):
    r = client.post("/api/summarize", json={"text": NOTES, "include": ["summary", "terms"], "length": "short"})
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Scripted Summary Title" and body["key_terms"][0]["term"] == "t"
    assert body["execution"]["path"][2] == "summarization_node" and body["processing"]["strategy"] == "single"
    assert llm.calls_for("summarize")[0].hints["include"] == ["summary", "terms"]
    assert "Scripted Summary Title" in [t["topic"] for t in client.get("/api/memory").json()["profile"]["topics_studied"]]


def test_long_document_uses_map_reduce_within_budget(client, llm):
    text = "\n\n".join(f"Section {i}. " + "The cell membrane regulates transport of molecules. " * 30 for i in range(12))
    r = client.post("/api/summarize", json={"text": text, "context_budget": 600})
    assert r.status_code == 200
    p = r.json()["processing"]
    assert p["strategy"] == "map-reduce" and p["chunks"] >= 2 and p["map_calls"] == p["chunks"] <= 8
    ctx = r.json()["execution"]["context"]
    assert ctx["tokens_after"] <= 600 and ctx["scope"] == "summarization_prompt"
    for call in llm.calls_for("summarize_chunk"):
        assert sum(len(str(m.content)) for m in call.messages) / 4 <= 700


@pytest.mark.parametrize("body", [{"text": "too short"}, {"text": NOTES, "include": []}, {"text": NOTES, "include": ["bogus"]},
                                  {"text": NOTES, "length": "huge"}])
def test_summarize_validation(client, body):
    assert client.post("/api/summarize", json=body).status_code == 422


def test_summary_inside_chat_is_rendered_as_markdown(client):
    body = chat(client, "Summarize this:\n" + NOTES * 2)
    content = body["message"]["content"]
    assert body["execution"]["intent"] == "summarization" and "### Key terms" in content and "| t | d |" in content


def test_summarize_with_no_material_in_chat_asks_for_it(client, llm):
    body = chat(client, "please summarize")
    assert "Paste the notes" in body["message"]["content"] and not llm.calls_for("summarize")


def test_offline_summary_is_genuinely_extractive(tmp_path):
    with TestClient(create_app(make_settings(tmp_path))) as c:
        body = c.post("/api/summarize", json={"text": NOTES * 3, "length": "short"}).json()
    assert "Photosynthesis" in body["summary"] or "Calvin" in body["summary"] or "Chloroplasts" in body["summary"]
    assert body["key_concepts"] and body["execution"]["llm"]["provider"] == "offline"


def test_offline_quiz_for_unknown_topic_explains_what_is_missing(tmp_path):
    with TestClient(create_app(make_settings(tmp_path))) as c:
        ok = c.post("/api/quiz/generate", json={"topic": "CPU scheduling", "num_questions": 3, "difficulty": "easy"}).json()
        assert len(ok["questions"]) == 3
        r = c.post("/api/quiz/generate", json={"topic": "medieval poetry", "num_questions": 3})
        assert r.status_code == 503 and "no quiz material" in r.json()["error"]["message"]
        too_many = c.post("/api/quiz/generate", json={"topic": "deadlock", "num_questions": 10}).json()
        assert len(too_many["questions"]) == 4 and "Only 4 of the 10" in too_many["warnings"][0]


# --------------------------------------------------------------------- upload
def upload(client, name, data):
    return client.post("/api/documents/extract", files={"file": (name, data)})


def test_upload_txt_md(client):
    r = upload(client, "notes.txt", NOTES.encode())
    assert r.status_code == 200 and r.json()["text"].startswith("Photosynthesis") and r.json()["info"]["extension"] == ".txt"
    assert upload(client, "n.md", b"# Title\nbody").json()["text"] == "# Title\nbody"


def test_upload_docx(client):
    doc = Document()
    doc.add_paragraph("Newton's laws describe motion.")
    table = doc.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text, table.rows[0].cells[1].text = "Force", "Mass times acceleration"
    buf = io.BytesIO()
    doc.save(buf)
    r = upload(client, "physics.docx", buf.getvalue())
    assert r.status_code == 200 and "Newton's laws" in r.json()["text"] and "Force | Mass times acceleration" in r.json()["text"]


def test_upload_pdf(client):
    r = upload(client, "a.pdf", minimal_pdf("Hello PDF world"))
    assert r.status_code == 200 and "Hello PDF world" in r.json()["text"] and r.json()["info"]["pages"] == 1


def test_upload_rejections(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, max_upload_bytes=2048), ScriptedLLM())) as c:
        assert upload(c, "x.exe", b"MZ").status_code == 422
        assert upload(c, "noext", b"hello").status_code == 422
        big = upload(c, "big.txt", b"a" * 5000)
        assert big.status_code == 413 and "limit" in big.json()["error"]["message"]
        assert upload(c, "empty.txt", b"").status_code == 422
        assert upload(c, "fake.pdf", b"not a pdf").status_code == 422
        assert upload(c, "fake.docx", b"not a zip").status_code == 422
        assert upload(c, "bin.txt", b"\x00\x01\x02binary").status_code == 422
        blank = PdfWriter()
        blank.add_blank_page(100, 100)
        buf = io.BytesIO()
        blank.write(buf)
        r = upload(c, "scan.pdf", buf.getvalue())
        assert r.status_code == 422 and "No extractable text" in r.json()["error"]["message"]
        assert c.post("/api/documents/extract").status_code == 422


def test_upload_truncates_to_max_chars(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, max_document_chars=100), ScriptedLLM())) as c:
        r = upload(c, "t.txt", b"word " * 200).json()
        assert r["info"]["truncated"] and r["info"]["characters"] == 999 and len(r["text"]) == 100


# ------------------------------------------------------------------ dashboard
def test_dashboard_only_contains_real_data(client):
    empty = client.get("/api/dashboard").json()
    assert empty["thread_count"] == 0 and empty["recent_topics"] == [] and empty["quiz"]["attempts"] == 0
    assert empty["quiz"]["average_percent"] is None and empty["runs_by_intent"] == {}
    chat(client, "Explain paging")
    chat(client, "Explain TLB")
    d = client.get("/api/dashboard").json()
    assert d["thread_count"] == 2 and {t["topic"] for t in d["recent_topics"]} == {"paging", "tlb"}
    assert d["runs_by_intent"] == {"explanation": 2} and len(d["recent_executions"]) == 2


def test_delete_all_user_data(client):
    chat(client, "I prefer concise answers.", user="zed")
    chat(client, "Explain paging", user="zed")
    r = client.delete("/api/user/data", headers={"X-User-Id": "zed"}).json()
    assert r["deleted_threads"] == 2  # each un-threaded chat call opened its own conversation
    assert client.get("/api/threads", headers={"X-User-Id": "zed"}).json() == []
    assert client.get("/api/memory", headers={"X-User-Id": "zed"}).json()["found"] is False


def test_bad_model_response_error_type_is_exposed():
    assert LLMResponseError("x").status_code == 502
