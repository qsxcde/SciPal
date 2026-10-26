"""Chat use case: one question in, a stream of transport-agnostic events out."""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

from backend.application import policies
from backend.application.events import (
    ChatEvent,
    DoneEvent,
    ErrorEvent,
    SourcesEvent,
    StatusEvent,
    TokenEvent,
    WarningEvent,
)
from backend.application.session_index import resolve_session_store
from backend.config import settings
from backend.domain.access import session_is_accessible
from backend.domain.exceptions import ActiveIndexNotReadyError, SessionNotFoundError
from backend.domain.models import SourceRef
from backend.rag import answer as chat_pipeline
from backend.storage.sqlite import messages as message_repo
from backend.storage.sqlite import sessions as session_repo
from backend.storage.sqlite.sessions import touch_session

logger = logging.getLogger(__name__)

STREAM_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="scipal-stream")

MISSING_SOURCES_EVENT_ERROR = "Stream protocol error: missing sources event from stream_answer()."


def _read_usage() -> dict | None:
    """Token usage of the stream that just finished (provider-dependent)."""
    from backend.adapters.llm.llm import last_usage

    return last_usage()


def _to_thread(fn, *args, **kwargs):
    """Wrap a sync call in asyncio.to_thread for non-blocking execution."""
    return asyncio.to_thread(fn, *args, **kwargs)


def _advance_stream_gen(gen):
    """Advance a generator on a thread, returning (done, value)."""
    try:
        return (False, next(gen))
    except StopIteration as e:
        return (True, e.value)


class StreamCollector:
    """Consume the RAG token stream, accumulating text and sources for persistence."""

    def __init__(self) -> None:
        self.tokens: list[str] = []
        self.sources: list[SourceRef] = []
        self.used_explicit_protocol = False
        self.received_sources = False
        self._warning: str = ""

    @property
    def warning(self) -> str:
        return self._warning

    @property
    def full_content(self) -> str:
        return "".join(self.tokens)

    def feed_token(self, token: str) -> TokenEvent:
        self.tokens.append(token)
        return TokenEvent(value=token)

    def feed_sources(self, value: Any) -> None:
        self.sources = _coerce_sources(value)
        self.received_sources = True

    async def consume_stream(self, stream) -> AsyncIterator[TokenEvent]:
        loop = asyncio.get_running_loop()
        gen = iter(stream)
        try:
            async for event in self._drain(gen, loop):
                yield event
        finally:
            # 取消/中断时释放同步生成器，避免挂起的 HTTP 响应继续计费
            close = getattr(gen, "close", None)
            if close is not None:
                close()

    async def _drain(self, gen, loop) -> AsyncIterator[TokenEvent]:
        while True:
            done, event = await loop.run_in_executor(STREAM_EXECUTOR, _advance_stream_gen, gen)
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
            if event["type"] == "warning":
                self._warning = event["value"]
                continue
            raise RuntimeError(f"Stream protocol error: unexpected event type {event['type']!r}.")

        if self.used_explicit_protocol and not self.received_sources:
            raise RuntimeError(MISSING_SOURCES_EVENT_ERROR)


_chat_locks: dict[str, asyncio.Lock] = {}


def _session_lock(session_id: str) -> asyncio.Lock:
    """One lock per session; the event loop serializes access to the dict."""
    lock = _chat_locks.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        _chat_locks[session_id] = lock
    return lock


async def stream_session_chat(
    session_id: str,
    content: str,
    wait_timeout_seconds: float | None = None,
    user_id: str | None = None,
    regenerate: bool = False,
    client_message_id: str | None = None,
) -> AsyncIterator[ChatEvent]:
    """Serialize turns within one session.

    Two tabs (or a regenerate racing a send) would otherwise interleave
    "delete previous answer / read history / persist answer".
    """
    async with _session_lock(session_id):
        inner: AsyncGenerator[ChatEvent, None] = _stream_session_chat(
            session_id,
            content,
            wait_timeout_seconds=wait_timeout_seconds,
            user_id=user_id,
            regenerate=regenerate,
            client_message_id=client_message_id,
        )
        try:
            async for event in inner:
                yield event
        except GeneratorExit:
            # 客户端中断：必须把 GeneratorExit 送进内层生成器，
            # 否则「落库为 stopped」的清理逻辑会被跳过。
            await inner.aclose()
            raise


async def _stream_session_chat(
    session_id: str,
    content: str,
    wait_timeout_seconds: float | None = None,
    user_id: str | None = None,
    regenerate: bool = False,
    client_message_id: str | None = None,
) -> AsyncGenerator[ChatEvent, None]:
    session = await _to_thread(session_repo.get_session, session_id)
    if not session_is_accessible(session, user_id):
        raise SessionNotFoundError(f"Session not found: {session_id}", session_id=session_id)

    state = StreamCollector()
    usage: dict | None = None
    pending_status_events: list[StatusEvent] = []
    try:
        store, _ = await resolve_session_store(
            session_id,
            wait_timeout_seconds=wait_timeout_seconds,
            on_wait_for_index=lambda: pending_status_events.append(
                StatusEvent(value="waiting_for_index")
            ),
        )
        for status_event in pending_status_events:
            yield status_event

        # 重新生成：复用已有提问，新答案写成功后才删旧答案。
        # 先删后写会在生成失败时永久丢失上一轮完整回答。
        replaced_answer_id: str | None = None
        if regenerate:
            previous = await _to_thread(message_repo.list_messages, session_id)
            if previous and previous[-1]["role"] == "assistant":
                replaced_answer_id = previous[-1]["id"]
        else:
            await _persist_and_touch(
                session_id, "user", content, client_message_id=client_message_id
            )

        # 历史在写入当前提问之后读取，重新生成时需要把这条提问排除掉
        history = await _to_thread(message_repo.list_messages, session_id)
        if regenerate and history and history[-1]["role"] == "user":
            history = history[:-1]

        yield StatusEvent(value="retrieving")
        yield StatusEvent(value="generating")
        stream = chat_pipeline.stream_answer(
            store,
            content,
            options=policies.retrieval_options(),
            policy=policies.answer_policy(),
            history=history,
        )

        try:
            async for token_event in state.consume_stream(stream):
                yield token_event
            usage = _read_usage()
        except (GeneratorExit, asyncio.CancelledError):
            # 客户端中止：把已生成的部分落库，避免刷新后这一轮凭空消失
            await _persist_interrupted_answer(session_id, state)
            raise

    except ActiveIndexNotReadyError as exc:
        async for event in _handle_active_index_not_ready(session_id, exc, pending_status_events):
            yield event
        return
    except Exception:
        logger.exception("Chat stream failed for session %s", session_id)
        async for event in _handle_stream_failure(session_id, state):
            yield event
        return

    await _persist_and_touch(
        session_id,
        "assistant",
        state.full_content,
        sources=state.sources,
        model=settings.deepseek_model,
        prompt_tokens=(usage or {}).get("prompt_tokens"),
        completion_tokens=(usage or {}).get("completion_tokens"),
    )
    if replaced_answer_id is not None:
        await _to_thread(message_repo.delete_message, replaced_answer_id)
    if state.warning:
        yield WarningEvent(value=state.warning)
    yield SourcesEvent(value=state.sources)
    yield DoneEvent()


async def _persist_and_touch(
    session_id: str,
    role: str,
    content: str,
    sources: list | None = None,
    status: str = "complete",
    client_message_id: str | None = None,
    model: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> None:
    await _to_thread(
        message_repo.create_message,
        session_id=session_id, role=role, content=content,
        sources=sources, status=status, client_message_id=client_message_id,
        model=model, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
    )
    await _to_thread(touch_session, session_id)


async def _persist_interrupted_answer(session_id: str, state: StreamCollector) -> None:
    """Best-effort persistence when the client aborts mid-stream."""
    if not state.full_content.strip():
        return
    try:
        # shield：取消域内仍要写完这条 stopped 消息
        await asyncio.shield(
            _persist_and_touch(
                session_id,
                "assistant",
                state.full_content,
                sources=state.sources,
                status="stopped",
            )
        )
    except BaseException:
        logger.warning("Failed to persist interrupted answer session=%s", session_id, exc_info=True)


async def _handle_active_index_not_ready(
    session_id: str,
    exc: ActiveIndexNotReadyError,
    pending_status_events: list[StatusEvent],
) -> AsyncIterator[ChatEvent]:
    """Yield events when no index snapshot is ready within timeout."""
    for status_event in pending_status_events:
        yield status_event
    error_message = str(exc) or settings.msg_index_not_ready
    await _persist_and_touch(session_id, "assistant", error_message, status="failed")
    yield TokenEvent(value=error_message)
    yield SourcesEvent(value=[])
    yield DoneEvent()


async def _handle_stream_failure(
    session_id: str,
    state: StreamCollector,
) -> AsyncIterator[ChatEvent]:
    """Yield events when an unexpected error occurs during streaming."""
    partial_content = state.full_content or ""
    await _persist_and_touch(session_id, "assistant", partial_content, status="failed")
    yield ErrorEvent(value="生成失败，请重试。")
    yield DoneEvent()


def _coerce_sources(value: Any) -> list[SourceRef]:
    return [
        source if isinstance(source, SourceRef) else SourceRef.model_validate(source)
        for source in value
    ]
