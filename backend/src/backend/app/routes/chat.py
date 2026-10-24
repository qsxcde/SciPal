import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from backend.app.security import get_current_user
from backend.app.services import session_service
from backend.app.services.chat_service import stream_session_chat
from backend.app.contracts import (
    ChatMessage,
    ChatStreamDoneEvent,
    ChatStreamErrorEvent,
    ChatStreamEvent,
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
    if session_service.get_accessible_session(session_id, user.get("id")) is None:
        raise HTTPException(status_code=404, detail="Session not found")
    events = stream_session_chat(
        session_id=session_id,
        content=message.content,
        user_id=user.get("id"),
    )

    async def generate():
        try:
            async for event in events:
                yield encode_sse_event(event)
        except asyncio.CancelledError:
            logger.info("SSE stream cancelled by client session=%s", session_id)
            return
        except Exception:
            logger.exception("Unhandled error in SSE stream session=%s", session_id)
            yield encode_sse_event(ChatStreamErrorEvent(type="error", value="internal_error"))
            yield encode_sse_event(ChatStreamDoneEvent(type="done"))

    return StreamingResponse(generate(), media_type="text/event-stream")
