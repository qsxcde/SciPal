import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

logger = logging.getLogger(__name__)

from backend.domain.config import settings
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
from backend.storage.sqlite.sessions import touch_session
from backend.rag.pipeline import online_pipeline as chat_pipeline
from backend.storage.vector_db import registry as index_registry

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


def _advance_stream_gen(gen):
    """Advance a generator on a thread, returning (done, value)."""
    try:
        return (False, next(gen))
    except StopIteration as e:
        return (True, e.value)


class _SSEStreamState:
    """Encapsulates SSE stream protocol state for a single chat turn."""

    def __init__(self) -> None:
        self.tokens: list[str] = []
        self.sources: list[SourceRef] = []
        self.used_explicit_protocol = False
        self.received_sources = False

    def feed_token(self, token: str) -> ChatStreamTokenEvent:
        self.tokens.append(token)
        return ChatStreamTokenEvent(type="token", value=token)

    def feed_sources(self, value: Any) -> None:
        self.sources = _coerce_sources(value)
        self.received_sources = True

    async def consume_stream(
        self,
        stream,
    ) -> AsyncIterator[ChatStreamTokenEvent]:
        loop = asyncio.get_running_loop()
        gen = iter(stream)
        while True:
            done, event = await loop.run_in_executor(None, _advance_stream_gen, gen)
            if done:
                if event is not None:
                    event = {"type": "_retval", "value": event}
                else:
                    break
            if isinstance(event, str):
                if self.used_explicit_protocol:
                    raise RuntimeError("Stream protocol error: mixed legacy and explicit stream events.")
                yield self.feed_token(event)
                continue

            if not isinstance(event, dict) or "type" not in event:
                raise RuntimeError("Stream protocol error: unsupported stream event payload.")

            if event["type"] == "_retval":
                if not self.used_explicit_protocol:
                    val = event.get("value")
                    if val is not None:
                        self.sources = _coerce_sources(val)
                continue
            self.used_explicit_protocol = True
            if event["type"] == "token":
                yield self.feed_token(event["value"])
                continue
            if event["type"] == "sources":
                self.feed_sources(event["value"])
                continue
            raise RuntimeError(f"Stream protocol error: unexpected event type {event['type']!r}.")

        if self.used_explicit_protocol and not self.received_sources:
            raise RuntimeError(MISSING_SOURCES_EVENT_ERROR)

    @property
    def full_content(self) -> str:
        return "".join(self.tokens)



async def stream_session_chat(
    session_id: str,
    content: str,
    wait_timeout_seconds: float | None = None,
) -> AsyncIterator[ChatStreamEvent]:
    if wait_timeout_seconds is None:
        wait_timeout_seconds = settings.index_max_wait
    session = await _to_thread(session_repo.get_session, session_id)
    if session is None or session["is_archived"]:
        raise SessionNotFoundError(f"Session not found: {session_id}")

    state = _SSEStreamState()
    pending_status_events: list[ChatStreamStatusEvent] = []
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
            session_id=session_id, role="user", content=content,
        )
        await _to_thread(touch_session, session_id)

        yield ChatStreamStatusEvent(type="status", value="retrieving")
        yield ChatStreamStatusEvent(type="status", value="generating")
        try:
            stream = chat_pipeline.stream_answer(
                store, content, options=production_retrieval_options(),
            )
        except TypeError:
            stream = chat_pipeline.stream_answer(store, content)

        async for token_event in state.consume_stream(stream):
            yield token_event

    except ActiveIndexNotReadyError as exc:
        for status_event in pending_status_events:
            yield status_event
        error_message = str(exc) or settings.msg_index_not_ready
        await _to_thread(
            message_repo.create_message,
            session_id=session_id, role="assistant", content=error_message, status="failed",
        )
        await _to_thread(touch_session, session_id)
        yield ChatStreamTokenEvent(type="token", value=error_message)
        yield ChatStreamSourcesEvent(type="sources", value=[])
        yield ChatStreamDoneEvent(type="done")
        return
    except Exception:
        logger.exception("Chat stream failed for session %s", session_id)
        partial_content = state.full_content or ""
        await _to_thread(
            message_repo.create_message,
            session_id=session_id, role="assistant", content=partial_content, status="failed",
        )
        await _to_thread(touch_session, session_id)
        yield ChatStreamErrorEvent(type="error", value="生成失败，请重试。")
        yield ChatStreamDoneEvent(type="done")
        return

    await _to_thread(
        message_repo.create_message,
        session_id=session_id, role="assistant", content=state.full_content,
        sources=state.sources, status="complete",
    )
    await _to_thread(touch_session, session_id)
    yield ChatStreamSourcesEvent(type="sources", value=state.sources)
    yield ChatStreamDoneEvent(type="done")


async def evaluate_session_chat(
    session_id: str,
    content: str,
    top_k: int = 5,
    wait_timeout_seconds: float | None = None,
    retrieval_options: RetrievalOptions | None = None,
) -> ChatEvaluationResult:
    if wait_timeout_seconds is None:
        wait_timeout_seconds = settings.index_max_wait
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
    wait_timeout_seconds: float | None = None,
    retrieval_options: RetrievalOptions | None = None,
) -> ChatEvaluationResult:
    if wait_timeout_seconds is None:
        wait_timeout_seconds = settings.index_max_wait
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
    backoff = settings.index_poll_interval
    while time.monotonic() < deadline:
        ready_snapshot = await _to_thread(snapshot_repo.get_active_ready_snapshot, session_id)
        if ready_snapshot is not None:
            return ready_snapshot
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, settings.index_poll_max_interval)
    raise ActiveIndexNotReadyError(settings.msg_index_not_ready)


def _coerce_sources(value: Any) -> list[SourceRef]:
    return [source if isinstance(source, SourceRef) else SourceRef.model_validate(source) for source in value]
