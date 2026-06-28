from fastapi import APIRouter, HTTPException
from backend.app.services import session_service
from backend.app.schemas.api import SessionCreateResponse, SessionSnapshot, SessionSummary, SessionUpdateRequest
from backend.storage.sqlite import sessions

router = APIRouter()


@router.get("/sessions", response_model=list[SessionSummary])
def list_sessions() -> list[dict]:
    return sessions.list_sessions()


@router.post("/sessions", response_model=SessionCreateResponse)
def create_session() -> SessionCreateResponse:
    return SessionCreateResponse(session_id=session_service.create_session())


@router.get("/sessions/{session_id}", response_model=SessionSnapshot)
def get_session(session_id: str) -> dict:
    snapshot = session_service.get_session_snapshot(session_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return snapshot


@router.patch("/sessions/{session_id}", response_model=SessionSummary)
def update_session(session_id: str, payload: SessionUpdateRequest) -> dict:
    summary = sessions.update_session(
        session_id=session_id,
        title=payload.title,
        is_pinned=payload.is_pinned,
    )
    if summary is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return summary


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str) -> dict:
    session_service.destroy_session(session_id)
    return {"status": "deleted"}
