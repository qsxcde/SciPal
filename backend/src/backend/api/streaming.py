"""SSE framing: application events -> transport models -> ``data:`` frames.

Also owns the heartbeat: a silent generator (slow LLM, index wait) would let a
reverse proxy or the browser drop an idle connection, so a comment frame is
emitted while nothing else is flowing.
"""

import asyncio
from collections.abc import AsyncIterator

from backend.api.schemas.chat import (
    ChatStreamDoneEvent,
    ChatStreamErrorEvent,
    ChatStreamEvent,
    ChatStreamSourcesEvent,
    ChatStreamStatusEvent,
    ChatStreamTokenEvent,
    ChatStreamWarningEvent,
)
from backend.application.events import (
    ChatEvent,
    DoneEvent,
    ErrorEvent,
    SourcesEvent,
    StatusEvent,
    TokenEvent,
    WarningEvent,
)


HEARTBEAT_FRAME = ": keep-alive\n\n"
HEARTBEAT_INTERVAL_SECONDS = 15.0
_STREAM_DONE = object()


async def _pump(source: AsyncIterator[ChatEvent], queue: "asyncio.Queue[object]") -> None:
    """Feed the queue from the source so the reader can apply a timeout."""
    try:
        async for event in source:
            await queue.put(event)
    except Exception as exc:  # re-raised on the consuming side
        await queue.put(exc)
    finally:
        await queue.put(_STREAM_DONE)


async def stream_with_heartbeat(
    events: AsyncIterator[ChatEvent],
    interval: float = HEARTBEAT_INTERVAL_SECONDS,
) -> AsyncIterator[str]:
    """Encode frames, emitting a heartbeat comment when the stream stalls."""
    queue: asyncio.Queue[object] = asyncio.Queue()
    pump = asyncio.create_task(_pump(events, queue))
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=interval)
            except TimeoutError:
                yield HEARTBEAT_FRAME
                continue
            if item is _STREAM_DONE:
                return
            if isinstance(item, Exception):
                raise item
            yield encode_sse_event(item)
    finally:
        pump.cancel()


def encode_sse_event(event: ChatEvent) -> str:
    return f"data: {to_transport_event(event).model_dump_json()}\n\n"


def to_transport_event(event: ChatEvent) -> ChatStreamEvent:
    if isinstance(event, StatusEvent):
        return ChatStreamStatusEvent(type="status", value=event.value)
    if isinstance(event, TokenEvent):
        return ChatStreamTokenEvent(type="token", value=event.value)
    if isinstance(event, SourcesEvent):
        return ChatStreamSourcesEvent(type="sources", value=event.value)
    if isinstance(event, WarningEvent):
        return ChatStreamWarningEvent(type="warning", value=event.value)
    if isinstance(event, ErrorEvent):
        return ChatStreamErrorEvent(type="error", value=event.value)
    if isinstance(event, DoneEvent):
        return ChatStreamDoneEvent(type="done")
    raise TypeError(f"Unsupported chat event: {type(event).__name__}")
