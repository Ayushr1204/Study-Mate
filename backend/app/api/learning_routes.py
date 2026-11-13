"""Quiz generation/evaluation, notes summarisation and document upload."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, UploadFile

from app.api.deps import get_runtime, get_user_id
from app.core.errors import UnprocessableError
from app.models.schemas import (
    DocumentExtractResponse,
    QuizGenerateRequest,
    QuizQuestionPublic,
    QuizResponse,
    QuizResultItem,
    QuizResultResponse,
    QuizSubmitRequest,
    SummarizeRequest,
    SummaryResponse,
)
from app.runtime import Runtime
from app.services.documents import extract_text
from app.services.runner import run_graph

router = APIRouter(tags=["learning tools"])

REVISION_THRESHOLD_PERCENT = 70


@router.post("/quiz/generate", response_model=QuizResponse, summary="Generate an MCQ quiz through the graph (quiz_node)")
def generate_quiz(body: QuizGenerateRequest, rt: Runtime = Depends(get_runtime), user: str = Depends(get_user_id)):
    thread = rt.db.create_thread(f"quiz-{uuid.uuid4().hex}", user, f"Quiz: {body.topic}", kind="quiz")
    values, record = run_graph(
        rt, user_id=user, thread_id=thread["id"], kind="quiz", forced_intent="quiz", budget=body.context_budget,
        text=f"Generate a {body.difficulty} quiz with {body.num_questions} questions on {body.topic}",
        payload={"topic": body.topic, "n": body.num_questions, "difficulty": body.difficulty},
    )
    quiz = values["generated_content"]["quiz"]
    quiz_id = uuid.uuid4().hex
    rt.db.save_quiz(quiz_id, user, quiz["topic"], quiz["difficulty"], quiz["questions"])
    return QuizResponse(
        quiz_id=quiz_id, topic=quiz["topic"], difficulty=quiz["difficulty"], requested=quiz["requested"],
        questions=[QuizQuestionPublic(question=q["question"], options=q["options"]) for q in quiz["questions"]],
        warnings=quiz["warnings"], execution=record,
    )


@router.get("/quizzes", summary="Quiz history")
def list_quizzes(rt: Runtime = Depends(get_runtime), user: str = Depends(get_user_id)):
    return rt.db.list_quizzes(user)


@router.post("/quizzes/{quiz_id}/submit", response_model=QuizResultResponse, summary="Evaluate answers (server-side)")
def submit_quiz(quiz_id: str, body: QuizSubmitRequest, rt: Runtime = Depends(get_runtime), user: str = Depends(get_user_id)):
    quiz = rt.db.get_quiz(user, quiz_id)
    questions = quiz["questions"]
    if len(body.answers) != len(questions):
        raise UnprocessableError(f"Expected {len(questions)} answers, got {len(body.answers)}.")
    if any(a is not None and not 0 <= a < 4 for a in body.answers):
        raise UnprocessableError("Each answer must be an option index from 0 to 3, or null to skip.")
    results = [
        QuizResultItem(
            question=q["question"], options=q["options"], selected=a, correct=q["answer_index"],
            is_correct=a == q["answer_index"], explanation=q.get("explanation", ""),
        )
        for q, a in zip(questions, body.answers, strict=True)
    ]
    score = sum(r.is_correct for r in results)
    percent = round(100 * score / len(questions))
    needs_revision = percent < REVISION_THRESHOLD_PERCENT
    rt.db.save_attempt(quiz_id, user, score, len(questions), body.answers)
    rt.profiles.update_revision(user, quiz["topic"], needs_revision)  # long-term memory: weak topics
    return QuizResultResponse(quiz_id=quiz_id, topic=quiz["topic"], score=score, total=len(questions),
                              percent=percent, results=results, needs_revision=needs_revision)


@router.post("/summarize", response_model=SummaryResponse, summary="Summarise notes through the graph (summarization_node)")
def summarize(body: SummarizeRequest, rt: Runtime = Depends(get_runtime), user: str = Depends(get_user_id)):
    thread = rt.db.create_thread(f"summary-{uuid.uuid4().hex}", user, "Notes summary", kind="summary")
    values, record = run_graph(
        rt, user_id=user, thread_id=thread["id"], kind="summary", forced_intent="summarization", budget=body.context_budget,
        text=body.text, payload={"include": body.include, "length": body.length},
    )
    gc = values["generated_content"]
    s = gc["summary"]
    return SummaryResponse(**s, processing=gc["processing"], execution=record)


@router.post("/documents/extract", response_model=DocumentExtractResponse, summary="Extract text from TXT/MD/PDF/DOCX")
async def extract_document(file: UploadFile, rt: Runtime = Depends(get_runtime)):
    limit = rt.settings.max_upload_bytes
    data = await file.read(limit + 1)
    text, info = extract_text(file.filename or "", data, max_bytes=limit, max_chars=rt.settings.max_document_chars)
    return DocumentExtractResponse(text=text, info=info)
