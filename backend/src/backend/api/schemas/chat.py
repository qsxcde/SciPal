"""Chat transport models: request payload and the SSE event union."""

from typing import Literal

from pydantic import BaseModel

from backend.domain.models import SourceRef


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"] = "user"
    content: str
    """为 true 时复用上一条用户提问，先删除旧回答再重新生成。"""
    regenerate: bool = False
    """客户端生成的消息 id，用于重试时去重（同一 id 只会落一条 user 消息）。"""
    client_message_id: str | None = None


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
