#!/usr/bin/env python3
"""Live end-to-end check of the five StudyMate demonstration workflows.

Starts a real uvicorn server (separate process, temporary data dir), drives it over HTTP, restarts it
to prove persistence, and asserts on the responses. Uses the offline provider by default so it runs
without a model; set E2E_PROVIDER=ollama to run against a local Ollama instead.

    python scripts/e2e_demo.py
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
PROVIDER = os.environ.get("E2E_PROVIDER", "offline")
results: list[tuple[str, bool, str]] = []


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    def __init__(self, data_dir: Path, port: int, **env: str):
        self.data_dir, self.port, self.extra = data_dir, port, env
        self.proc: subprocess.Popen | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/api"

    def start(self) -> None:
        env = {**os.environ, "STUDYMATE_DATA_DIR": str(self.data_dir), "LLM_PROVIDER": PROVIDER, "TOKEN_COUNTER": "auto", **self.extra}
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app_factory", "--factory", "--host", "127.0.0.1", "--port", str(self.port), "--log-level", "warning"],
            cwd=BACKEND, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        for _ in range(100):
            if self.proc.poll() is not None:
                raise RuntimeError("server exited:\n" + (self.proc.stdout.read().decode() if self.proc.stdout else ""))
            try:
                if httpx.get(f"{self.url}/health", timeout=1).status_code == 200:
                    return
            except httpx.HTTPError:
                time.sleep(0.2)
        raise RuntimeError("server did not become healthy")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not ok else ""))


def chat(c: httpx.Client, user: str, message: str, thread: str | None = None, **extra) -> dict:
    r = c.post("/chat", headers={"X-User-Id": user}, json={"thread_id": thread, "message": message, **extra}, timeout=180)
    r.raise_for_status()
    return r.json()


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="studymate-e2e-"))
    srv = Server(tmp, free_port())
    try:
        srv.start()
        h = httpx.get(f"{srv.url}/health").json()
        print(f"server up: provider={PROVIDER} token_counter={h['token_counter']} version={h['version']}")
        c = httpx.Client(base_url=srv.url)
        U = {"X-User-Id": "alice"}

        print("\nDemo 1 - long-term memory across threads (and restart)")
        a = chat(c, "alice", "I prefer explanations using real-world analogies")
        check("thread A routed to preference/general", a["execution"]["intent"] in ("preference", "general"), str(a["execution"]["intent"]))
        mem = c.get("/memory", headers=U).json()
        check("profile stored in Store", "analog" in (mem["profile"]["preferred_explanation_style"] or "").lower(), str(mem["profile"]))
        b = chat(c, "alice", "Explain CPU scheduling")
        check("thread B is a different thread", a["thread_id"] != b["thread_id"])
        check("thread B retrieved memory", b["execution"]["retrieved_memory"].get("found") is True)
        check("thread B answer follows the stored style", any(w in b["message"]["content"].lower() for w in ("analog", "like a", "imagine", "think of")), b["message"]["content"][:120])
        other = c.get("/memory", headers={"X-User-Id": "bob"}).json()
        check("another user's namespace is empty", not other["found"])
        srv.stop(); srv.start()
        mem2 = httpx.get(f"{srv.url}/memory", headers=U).json()
        check("profile survives a server restart", mem2["profile"]["preferred_explanation_style"] == mem["profile"]["preferred_explanation_style"])
        c = httpx.Client(base_url=srv.url)

        print("\nDemo 2 - short-term state, checkpoints, thread isolation")
        t1 = chat(c, "alice", "Explain deadlock")
        t1b = chat(c, "alice", "Explain virtual memory", thread=t1["thread_id"])
        st = c.get(f"/threads/{t1['thread_id']}/state", headers=U).json()
        check("messages accumulate within a thread (4)", st["message_count"] == 4, str(st["message_count"]))
        check("multiple checkpoints recorded", len(st["checkpoints"]) >= 4, str(len(st["checkpoints"])))
        t2 = chat(c, "alice", "Explain recursion")
        st2 = c.get(f"/threads/{t2['thread_id']}/state", headers=U).json()
        check("second thread is isolated (2 messages)", st2["message_count"] == 2, str(st2["message_count"]))
        topics = {i["topic"] for i in st["values"]["learning_insights"]}
        check("insights reducer collected both topics", len(topics) >= 2, str(topics))
        check("trace was reset for the latest run", len(st["values"]["execution_metadata"]["trace"]) == len(t1b["execution"]["path"]))
        check("cross-user thread access is refused", c.get(f"/threads/{t1['thread_id']}", headers={"X-User-Id": "bob"}).status_code == 404)

        print("\nDemo 3 - context window management")
        small = 300
        th = None
        for i in range(4):
            r = chat(c, "alice", f"Explain binary search part {i}: " + ("detail " * 120), thread=th, context_budget=small)
            th = r["thread_id"]
        ctx = r["execution"]["context"]
        check("tokens_after within budget", ctx["tokens_after"] <= small and ctx["within_budget"], str(ctx))
        check("older messages were trimmed", ctx["trimmed_messages"] > 0 or ctx["truncated_messages"] > 0, str(ctx))
        check("latest message always kept", ctx["decisions"][-1][0] == "retained", str(ctx["decisions"][-2:]))
        check("stats name the token counter", bool(ctx["token_counter"]))

        print("\nDemo 4 - quiz, grading and revision memory")
        q = c.post("/quiz/generate", headers=U, json={"topic": "Deadlock", "difficulty": "easy", "num_questions": 3}, timeout=180).json()
        check("quiz generated through the graph", "quiz_node" in q["execution"]["path"], str(q["execution"]["path"]))
        check("answers are not sent to the client", all("correct" not in x and "answer" not in x for x in q["questions"]))
        wrong = c.post(f"/quizzes/{q['quiz_id']}/submit", headers=U, json={"answers": [None] * len(q["questions"])}).json()
        check("server grades the submission", wrong["score"] == 0 and wrong["needs_revision"])
        check("weak topic stored in revision_areas", any("deadlock" in r.lower() for r in c.get("/memory", headers=U).json()["profile"]["revision_areas"]))

        print("\nDemo 5 - document summarisation and graph introspection")
        notes = ("Operating systems manage hardware resources. A process is a program in execution. "
                 "The scheduler decides which process runs next. Deadlock occurs when processes wait on each other forever. "
                 "Virtual memory lets programs use more memory than is physically installed. ") * 6
        ex = c.post("/documents/extract", headers=U, files={"file": ("notes.txt", notes.encode(), "text/plain")}).json()
        check("TXT upload extracted", ex["info"]["characters"] > 200)
        s = c.post("/summarize", headers=U, json={"text": ex["text"], "include": ["summary", "concepts", "revision"], "length": "short"}, timeout=180).json()
        check("summary produced via summarization_node", "summarization_node" in s["execution"]["path"] and bool(s["summary"]))
        g = c.get("/graph").json()
        names = {n["id"] for n in g["nodes"]}
        check("graph exposes all required nodes", {"load_memory_node", "router_node", "explanation_node", "quiz_node", "summarization_node", "response_node", "memory_update_node"} <= names)
        check("graph has conditional edges", any(e["conditional"] for e in g["edges"]))
        check("at least two reducers reported", len(g["reducers"]) >= 2)

        print("\nNegative paths")
        check("missing thread -> 404 structured error", c.get("/threads/nope", headers=U).json()["error"]["code"])
        check("invalid user id rejected", c.get("/threads", headers={"X-User-Id": "../etc"}).status_code == 400)
        check("empty message rejected", c.post("/chat", headers=U, json={"message": "   "}).status_code == 422)
        c.delete("/user/data", headers=U)
        check("delete-all-data clears profile", not c.get("/memory", headers=U).json()["found"])
    finally:
        srv.stop()
        shutil.rmtree(tmp, ignore_errors=True)

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
