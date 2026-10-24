"""Evaluation use cases used by the offline CLI (never by the HTTP API)."""

import asyncio

from backend.application import policies
from backend.application.session_index import resolve_session_store
from backend.rag.answer import ChatEvaluationResult, RetrievalOptions
from backend.rag import answer as chat_pipeline


async def evaluate_session_chat(
    session_id: str,
    content: str,
    top_k: int = 5,
    wait_timeout_seconds: float | None = None,
    retrieval_options: RetrievalOptions | None = None,
) -> ChatEvaluationResult:
    store, _ = await resolve_session_store(
        session_id,
        wait_timeout_seconds=wait_timeout_seconds,
    )
    return await asyncio.to_thread(
        chat_pipeline.evaluate_answer,
        store,
        content,
        k=top_k,
        options=retrieval_options,
        policy=policies.answer_policy(),
    )


async def evaluate_session_retrieval(
    session_id: str,
    content: str,
    top_k: int = 5,
    wait_timeout_seconds: float | None = None,
    retrieval_options: RetrievalOptions | None = None,
) -> ChatEvaluationResult:
    store, _ = await resolve_session_store(
        session_id,
        wait_timeout_seconds=wait_timeout_seconds,
    )
    return await asyncio.to_thread(
        chat_pipeline.evaluate_retrieval,
        store,
        content,
        k=top_k,
        options=retrieval_options or policies.retrieval_options(),
    )
