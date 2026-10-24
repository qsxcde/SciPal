import asyncio
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from backend.api.deps import get_accessible_session
from backend.api.schemas import ChatMessage
from backend.api.security import get_current_user
from backend.api.streaming import encode_sse_event
from backend.application.chat import stream_session_chat
from backend.application.events import DoneEvent, ErrorEvent

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/sessions/{session_id}/messages")
async def chat(
    session_id: str,
    message: ChatMessage,
    session: dict = Depends(get_accessible_session),
    user: dict = Depends(get_current_user),
) -> StreamingResponse:
    events = stream_session_chat(
        session_id=session["id"],
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
            yield encode_sse_event(ErrorEvent(value="internal_error"))
            yield encode_sse_event(DoneEvent())

    return StreamingResponse(generate(), media_type="text/event-stream")
