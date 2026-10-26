from __future__ import annotations

from typing import TYPE_CHECKING

from backend.domain.access import session_is_accessible
from backend.config import settings
from backend.domain.exceptions import SessionNotFoundError
from backend.domain.states import DocumentStage, PROCESSING_DOCUMENT_STAGES, SessionStatus
from backend.storage.sqlite import chunks
from backend.storage.sqlite import documents
from backend.storage.sqlite import index_snapshots
from backend.storage.sqlite import indexes
from backend.storage.sqlite import jobs
from backend.storage.sqlite import messages
from backend.storage.sqlite import sessions
from backend.adapters.vector import store_cache
from backend.storage.paths import remove_session_dir

if TYPE_CHECKING:
    from backend.rag.indexing.vector_store import AbstractVectorStore


def create_session(user_id: str | None = None) -> str:
    session = sessions.create_session(title=settings.msg_default_session_title, user_id=user_id)
    return session["id"]


def list_sessions(user_id: str | None = None) -> list[dict]:
    return sessions.list_sessions(user_id=user_id)


def update_session(
    session_id: str,
    title: str | None = None,
    is_pinned: bool | None = None,
) -> dict | None:
    return sessions.update_session(session_id=session_id, title=title, is_pinned=is_pinned)


def get_accessible_session(session_id: str, user_id: str | None) -> dict | None:
    """Return the session row only when it exists, is not archived and is owned by ``user_id``.

    ``sessions.user_id`` may be NULL for sessions created while authentication was
    disabled (development bypass); such legacy rows stay readable by any caller.
    """
    session = sessions.get_session(session_id)
    if not session_is_accessible(session, user_id):
        return None
    return session


def get_session_snapshot(session_id: str, user_id: str | None = None) -> dict | None:
    session = get_accessible_session(session_id, user_id)
    if session is None:
        return None
    session_documents = documents.list_documents(session_id)
    session_messages = messages.list_messages(session_id)
    return _build_session_snapshot(
        session={
            **session,
            "status": _derive_session_status(session_documents),
        },
        documents=session_documents,
        messages=session_messages,
        indexed_chunks=chunks.count_chunks(session_id),
        retrieval_index=indexes.get_index(session_id),
        active_index=index_snapshots.get_active_ready_snapshot(session_id),
        jobs=jobs.list_jobs_for_session(session_id),
    )


def _derive_session_status(session_documents: list[dict]) -> str:
    if not session_documents:
        return SessionStatus.empty
    statuses = {document["status"] for document in session_documents}
    if any(status in PROCESSING_DOCUMENT_STAGES for status in statuses):
        return SessionStatus.processing
    if statuses == {DocumentStage.ready}:
        return SessionStatus.ready
    if DocumentStage.failed in statuses and DocumentStage.ready in statuses:
        return SessionStatus.degraded
    if statuses == {DocumentStage.failed}:
        return SessionStatus.failed
    return SessionStatus.processing


def _build_session_snapshot(
    *,
    session: dict,
    documents: list[dict],
    messages: list[dict],
    indexed_chunks: int,
    retrieval_index: dict | None,
    active_index: dict | None,
    jobs: list[dict],
) -> dict:
    snapshot = dict(session)
    snapshot["documents"] = documents
    snapshot["messages"] = messages
    snapshot["indexed_chunks"] = indexed_chunks
    snapshot["retrieval_index"] = retrieval_index
    snapshot["active_index"] = active_index
    snapshot["jobs"] = jobs
    snapshot["status"] = session.get("status") or _derive_session_status(documents)
    return snapshot


def get_store(session_id: str) -> AbstractVectorStore:
    session = sessions.get_session(session_id)
    if session is None or session["is_archived"]:
        raise SessionNotFoundError(f"Session not found: {session_id}")
    return store_cache.get_store(session_id)


def destroy_session(session_id: str) -> None:
    if jobs.has_running_job(session_id):
        from backend.domain.exceptions import JobInProgressError

        raise JobInProgressError(
            "Session is still being processed, try again later.", session_id=session_id
        )
    sessions.archive_session(session_id)
    store_cache.discard_store(session_id)
    remove_session_dir(session_id)
