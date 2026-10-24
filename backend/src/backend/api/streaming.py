"""SSE framing: application events -> transport models -> ``data:`` frames."""

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
