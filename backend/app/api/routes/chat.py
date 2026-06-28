import asyncio
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from backend.app.core.auth import get_current_user
from backend.app.services.chat_service import stream_session_chat
from backend.app.schemas.api import (
    ChatMessage,
    ChatStreamDoneEvent,
    ChatStreamErrorEvent,
    ChatStreamEvent,
    ChatStreamSourcesEvent,
    ChatStreamStatusEvent,
    ChatStreamTokenEvent,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def encode_sse_event(payload: ChatStreamEvent) -> str:
    return f"data: {payload.model_dump_json()}\n\n"


@router.post("/sessions/{session_id}/messages")
async def chat(
    session_id: str,
    message: ChatMessage,
    user: dict = Depends(get_current_user),
) -> StreamingResponse:
    events = stream_session_chat(session_id=session_id, content=message.content)

    async def generate():
        try:
            async for event in events:
                yield encode_sse_event(event)
        except asyncio.CancelledError:
            logger.info("SSE stream cancelled by client session=%s", session_id)
            return
        except Exception as exc:
            logger.exception("Unhandled error in SSE stream session=%s", session_id)
            yield encode_sse_event(ChatStreamErrorEvent(type="error", value="internal_error"))
            yield encode_sse_event(ChatStreamDoneEvent(type="done"))

    return StreamingResponse(generate(), media_type="text/event-stream")
