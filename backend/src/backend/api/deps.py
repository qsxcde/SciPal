"""Reusable FastAPI dependencies (authorization lives here, once)."""

from fastapi import Depends

from backend.api.security import get_current_user
from backend.application import sessions as session_service
from backend.domain.exceptions import SessionNotFoundError


def get_accessible_session(
    session_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Resolve a session the caller may access, or fail with a domain error.

    Keeping this in one dependency guarantees that every route applies the same
    ownership rule and that the 404 response is produced by a single handler.
    """
    session = session_service.get_accessible_session(session_id, user.get("id"))
    if session is None:
        raise SessionNotFoundError(f"Session not found: {session_id}", session_id=session_id)
    return session
