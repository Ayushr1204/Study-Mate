"""Summarisation of study material, with map-reduce for documents that exceed the context budget."""

from __future__ import annotations

import re
from typing import Any

from langchain_core.messages import HumanMessage

from app.core.tokens import TokenCounter
from app.graph.context import build_context
from app.graph.prompts import CHUNK_SYSTEM, summary_system
from app.llm.base import LLMProvider, LLMResult
from app.models.content import SummaryOutput
from app.services.structured import call_json

MAX_CHUNKS = 8
OUTPUT_RESERVE = 64


def chunk_text(text: str, counter: TokenCounter, max_tokens: int) -> list[str]:
    """Split on paragraph boundaries into chunks of at most max_tokens (hard-splitting oversized paragraphs)."""
    pieces: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if counter.count_text(para) <= max_tokens:
            pieces.append(para)
            continue
        step = max(200, max_tokens * 3)
        pieces.extend(para[i : i + step] for i in range(0, len(para), step))
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current}\n\n{piece}" if current else piece
        if current and counter.count_text(candidate) > max_tokens:
            chunks.append(current)
            current = piece
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def summarize_document(
    llm: LLMProvider,
    counter: TokenCounter,
    text: str,
    *,
    include: list[str],
    length: str,
    profile: dict[str, Any],
    budget: int,
) -> tuple[SummaryOutput, dict[str, Any], LLMResult, dict[str, Any]]:
    """Returns (summary, context stats of the final call, final LLMResult, processing info)."""
    system = summary_system(include, length, profile)
    sys_tokens = counter.count_message(HumanMessage(content=system))
    available = max(budget - sys_tokens - OUTPUT_RESERVE, 100)
    doc_tokens = counter.count_text(text)
    info: dict[str, Any] = {"document_tokens": doc_tokens, "strategy": "single", "chunks": 1, "map_calls": 0, "document_truncated": False}
    source = text

    if doc_tokens > available:
        chunk_limit = max(150, min(available - 80, 2000))
        chunks = chunk_text(text, counter, chunk_limit)
        if len(chunks) > MAX_CHUNKS:
            chunks, info["document_truncated"] = chunks[:MAX_CHUNKS], True
        notes: list[str] = []
        for chunk in chunks:
            ctx = build_context([HumanMessage(content=chunk)], CHUNK_SYSTEM, budget=budget, max_message_tokens=chunk_limit + 8, counter=counter)
            res = llm.invoke(ctx.messages, task="summarize_chunk", temperature=0.2, hints={"text": chunk})
            notes.append(res.text.strip())
        source = "\n\n".join(notes)
        info.update(strategy="map-reduce", chunks=len(chunks), map_calls=len(chunks))

    ctx = build_context([HumanMessage(content=source)], system, budget=budget, max_message_tokens=available, counter=counter)
    summary, result, attempts = call_json(
        llm, ctx.messages, SummaryOutput, task="summarize", hints={"text": source, "include": include, "length": length}
    )
    info["attempts"] = attempts
    return summary, ctx.stats, result, info
