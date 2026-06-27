import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

logger = logging.getLogger(__name__)

from backend.domain.exceptions import ActiveIndexNotReadyError
from backend.domain.exceptions import SessionNotFoundError
from backend.app.schemas.api import ChatStreamDoneEvent
from backend.app.schemas.api import ChatStreamErrorEvent
from backend.app.schemas.api import ChatStreamEvent
from backend.app.schemas.api import ChatStreamSourcesEvent
from backend.app.schemas.api import ChatStreamStatusEvent
from backend.app.schemas.api import ChatStreamTokenEvent
from backend.rag.ingestion.metadata import SourceRef
from backend.rag.pipeline.online_pipeline import ChatEvaluationResult
from backend.rag.pipeline.online_pipeline import RetrievalOptions
from backend.storage.sqlite import index_snapshots as snapshot_repo
from backend.storage.sqlite import messages as message_repo
from backend.storage.sqlite import sessions as session_repo
from backend.rag.pipeline import online_pipeline as chat_pipeline
from backend.storage.vector_db import registry as index_registry

READY_INDEX_POLL_INTERVAL_SECONDS = 0.05
READY_INDEX_MAX_POLL_INTERVAL_SECONDS = 1.0
READY_INDEX_MAX_WAIT_SECONDS = 10.0
INDEX_NOT_READY_MESSAGE = "论文仍在处理中，请稍后重试。"
MISSING_SOURCES_EVENT_ERROR = "Stream protocol error: missing sources event from stream_answer()."

def production_retrieval_options() -> RetrievalOptions:
    return RetrievalOptions(
        strategy="hybrid",
        bm25_top_k=5,
        dense_top_k=5,
        seed_top_k=5,
        rrf_k=60,
        max_expanded_chunks=8,
        same_section_window=0,
        adjacent_window=1,
        include_linked_blocks=False,
    )


def _to_thread(fn, *args, **kwargs):
    """Wrap a sync call in asyncio.to_thread for non-blocking execution."""
    return asyncio.to_thread(fn, *args, **kwargs)



async def stream_session_chat(
    session_id: str,
    content: str,
    wait_timeout_seconds: float = READY_INDEX_MAX_WAIT_SECONDS,
) -> AsyncIterator[ChatStreamEvent]:
    session = await _to_thread(session_repo.get_session, session_id)
    if session is None or session["is_archived"]:
        raise SessionNotFoundError(f"Session not found: {session_id}")

    tokens: list[str] = []
    sources: list[SourceRef] = []
    pending_status_events: list[ChatStreamStatusEvent] = []
    used_explicit_stream_protocol = False
    received_sources_event = False
    try:
        store, _ = await _resolve_session_store(
            session_id,
            wait_timeout_seconds=wait_timeout_seconds,
            on_wait_for_index=lambda: pending_status_events.append(
                ChatStreamStatusEvent(type="status", value="waiting_for_index")
            ),
        )
        for status_event in pending_status_events:
            yield status_event

        await _to_thread(
            message_repo.create_message,
            session_id=session_id,
            role="user",
            content=content,
        )

        yield ChatStreamStatusEvent(type="status", value="retrieving")
        yield ChatStreamStatusEvent(type="status", value="generating")
        try:
            stream = chat_pipeline.stream_answer(
                store,
                content,
                options=production_retrieval_options(),
            )
        except TypeError:
            stream = chat_pipeline.stream_answer(store, content)

        def _advance_gen(gen):
            try:
                return (False, next(gen))
            except StopIteration as e:
                return (True, e.value)

        loop = asyncio.get_running_loop()
        _gen = iter(stream)
        while True:
            done, event = await loop.run_in_executor(None, _advance_gen, _gen)
            if done:
                if event is not None:
                    event = {"type": "_retval", "value": event}
                else:
                    break
            if isinstance(event, str):
                if used_explicit_stream_protocol:
                    raise RuntimeError("Stream protocol error: mixed legacy and explicit stream events.")
                tokens.append(event)
                yield ChatStreamTokenEvent(type="token", value=event)
                continue

            if not isinstance(event, dict) or "type" not in event:
                raise RuntimeError("Stream protocol error: unsupported stream event payload.")

            if event["type"] == "_retval":
                if not used_explicit_stream_protocol:
                    val = event.get("value")
                    if val is not None:
                        sources = _coerce_sources(val)
                continue
            used_explicit_stream_protocol = True
            if event["type"] == "token":
                token = event["value"]
                tokens.append(token)
                yield ChatStreamTokenEvent(type="token", value=token)
                continue
            if event["type"] == "sources":
                sources = _coerce_sources(event["value"])
                received_sources_event = True
                continue
            raise RuntimeError(f"Stream protocol error: unexpected event type {event['type']!r}.")

        if used_explicit_stream_protocol and not received_sources_event:
            raise RuntimeError(MISSING_SOURCES_EVENT_ERROR)
    except ActiveIndexNotReadyError as exc:
        for status_event in pending_status_events:
            yield status_event
        error_message = str(exc) or INDEX_NOT_READY_MESSAGE
        await _to_thread(
            message_repo.create_message,
            session_id=session_id,
            role="assistant",
            content=error_message,
            status="failed",
        )
        yield ChatStreamTokenEvent(type="token", value=error_message)
        yield ChatStreamSourcesEvent(type="sources", value=[])
        yield ChatStreamDoneEvent(type="done")
        return
    except Exception:
        logger.exception("Chat stream failed for session %s", session_id)
        partial_content = "".join(tokens) if tokens else ""
        await _to_thread(
            message_repo.create_message,
            session_id=session_id,
            role="assistant",
            content=partial_content,
            status="failed",
        )
        yield ChatStreamErrorEvent(type="error", value="生成失败，请重试。")
        yield ChatStreamDoneEvent(type="done")
        return

    await _to_thread(
        message_repo.create_message,
        session_id=session_id,
        role="assistant",
        content="".join(tokens),
        sources=sources,
        status="complete",
    )
    yield ChatStreamSourcesEvent(type="sources", value=sources)
    yield ChatStreamDoneEvent(type="done")


async def evaluate_session_chat(
    session_id: str,
    content: str,
    top_k: int = 5,
    wait_timeout_seconds: float = READY_INDEX_MAX_WAIT_SECONDS,
    retrieval_options: RetrievalOptions | None = None,
) -> ChatEvaluationResult:
    store, _ = await _resolve_session_store(
        session_id,
        wait_timeout_seconds=wait_timeout_seconds,
    )
    return await _to_thread(
        chat_pipeline.evaluate_answer,
        store,
        content,
        k=top_k,
        options=retrieval_options,
    )


async def evaluate_session_retrieval(
    session_id: str,
    content: str,
    top_k: int = 5,
    wait_timeout_seconds: float = READY_INDEX_MAX_WAIT_SECONDS,
    retrieval_options: RetrievalOptions | None = None,
) -> ChatEvaluationResult:
    store, _ = await _resolve_session_store(
        session_id,
        wait_timeout_seconds=wait_timeout_seconds,
    )
    return await _to_thread(
        chat_pipeline.evaluate_retrieval,
        store,
        content,
        k=top_k,
        options=retrieval_options,
    )


async def _resolve_session_store(
    session_id: str,
    wait_timeout_seconds: float,
    on_wait_for_index: Callable[[], None] | None = None,
) -> tuple[object, bool]:
    session = await _to_thread(session_repo.get_session, session_id)
    if session is None or session["is_archived"]:
        raise SessionNotFoundError(f"Session not found: {session_id}")

    ready_snapshot = await _to_thread(snapshot_repo.get_active_ready_snapshot, session_id)
    waited_for_index = False
    if ready_snapshot is None:
        waited_for_index = True
        if on_wait_for_index is not None:
            on_wait_for_index()
        ready_snapshot = await _wait_for_ready_index(
            session_id,
            timeout_seconds=wait_timeout_seconds,
        )

    return index_registry.get_store_for_snapshot(ready_snapshot), waited_for_index


async def _wait_for_ready_index(session_id: str, timeout_seconds: float) -> dict | None:
    deadline = time.monotonic() + timeout_seconds
    backoff = READY_INDEX_POLL_INTERVAL_SECONDS
    while time.monotonic() < deadline:
        ready_snapshot = await _to_thread(snapshot_repo.get_active_ready_snapshot, session_id)
        if ready_snapshot is not None:
            return ready_snapshot
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, READY_INDEX_MAX_POLL_INTERVAL_SECONDS)
    raise ActiveIndexNotReadyError(INDEX_NOT_READY_MESSAGE)


def _coerce_sources(value: Any) -> list[SourceRef]:
    return [source if isinstance(source, SourceRef) else SourceRef.model_validate(source) for source in value]
