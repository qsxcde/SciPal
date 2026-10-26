import asyncio
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from backend.api.deps import get_accessible_session
from backend.api.schemas import ChatMessage
from backend.api.security import get_current_user
from backend.api.streaming import encode_sse_event, stream_with_heartbeat
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
    """发送提问，以 text/event-stream 流式返回回答。"""
    events = stream_session_chat(
        session_id=session["id"],
        content=message.content,
        user_id=user.get("id"),
        regenerate=message.regenerate,
        client_message_id=message.client_message_id,
    )

    async def generate():
        try:
            async for frame in stream_with_heartbeat(events):
                yield frame
        except asyncio.CancelledError:
            logger.info("SSE stream cancelled by client session=%s", session_id)
            return
        except Exception:
            logger.exception("Unhandled error in SSE stream session=%s", session_id)
            yield encode_sse_event(ErrorEvent(value="internal_error"))
            yield encode_sse_event(DoneEvent())

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # nginx 默认缓冲会让流式退化成「等全部生成完再吐」，必须显式关闭
            "X-Accel-Buffering": "no",
        },
    )
