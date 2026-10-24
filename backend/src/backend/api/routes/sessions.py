from fastapi import APIRouter, Depends

from backend.api.deps import get_accessible_session
from backend.api.schemas import (
    SessionCreateResponse,
    SessionSnapshot,
    SessionSummary,
    SessionUpdateRequest,
)
from backend.api.security import get_current_user
from backend.application import sessions as session_service
from backend.domain.exceptions import SessionNotFoundError

router = APIRouter()


@router.get("/sessions", response_model=list[SessionSummary])
def list_sessions(user: dict = Depends(get_current_user)) -> list[dict]:
    return session_service.list_sessions(user_id=user.get("id") or None)


@router.post("/sessions", response_model=SessionCreateResponse)
def create_session(user: dict = Depends(get_current_user)) -> SessionCreateResponse:
    return SessionCreateResponse(
        session_id=session_service.create_session(user_id=user.get("id") or None)
    )


@router.get("/sessions/{session_id}", response_model=SessionSnapshot)
def get_session(session_id: str, user: dict = Depends(get_current_user)) -> dict:
    snapshot = session_service.get_session_snapshot(session_id, user_id=user.get("id"))
    if snapshot is None:
        raise SessionNotFoundError(f"Session not found: {session_id}", session_id=session_id)
    return snapshot


@router.patch("/sessions/{session_id}", response_model=SessionSummary)
def update_session(
    session_id: str,
    payload: SessionUpdateRequest,
    _session: dict = Depends(get_accessible_session),
) -> dict:
    summary = session_service.update_session(
        session_id=session_id,
        title=payload.title,
        is_pinned=payload.is_pinned,
    )
    if summary is None:
        raise SessionNotFoundError(f"Session not found: {session_id}", session_id=session_id)
    return summary


@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    # Intentionally idempotent: deleting an unknown or foreign session is a no-op
    # and must not reveal whether the session exists.
    if session_service.get_accessible_session(session_id, user.get("id")) is not None:
        session_service.destroy_session(session_id)
    return {"status": "deleted"}
