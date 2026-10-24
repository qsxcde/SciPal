"""Chat transport models: request payload and the SSE event union."""

from typing import Literal

from pydantic import BaseModel

from backend.domain.models import SourceRef


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"] = "user"
    content: str


class ChatStreamTokenEvent(BaseModel):
    type: Literal["token"]
    value: str


class ChatStreamStatusEvent(BaseModel):
    type: Literal["status"]
    value: Literal["waiting_for_index", "retrieving", "generating"]


class ChatStreamSourcesEvent(BaseModel):
    type: Literal["sources"]
    value: list[SourceRef]


class ChatStreamErrorEvent(BaseModel):
    type: Literal["error"]
    value: str


class ChatStreamWarningEvent(BaseModel):
    type: Literal["warning"]
    value: str


class ChatStreamDoneEvent(BaseModel):
    type: Literal["done"]


ChatStreamEvent = (
    ChatStreamStatusEvent
    | ChatStreamTokenEvent
    | ChatStreamSourcesEvent
    | ChatStreamErrorEvent
    | ChatStreamWarningEvent
    | ChatStreamDoneEvent
)
