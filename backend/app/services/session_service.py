from backend.domain.config import settings
from backend.rag.indexing.vector_store import AbstractVectorStore
from backend.domain.exceptions import SessionNotFoundError
from backend.domain.states import DocumentStage, SessionStatus
from backend.storage.sqlite import chunks
from backend.storage.sqlite import documents
from backend.storage.sqlite import index_snapshots
from backend.storage.sqlite import indexes
from backend.storage.sqlite import jobs
from backend.storage.sqlite import messages
from backend.storage.sqlite import sessions
from backend.storage.vector_db import registry as index_registry
from backend.storage.paths import remove_session_dir


def create_session(user_id: str | None = None) -> str:
    session = sessions.create_session(title=settings.msg_default_session_title, user_id=user_id)
    return session["id"]


def get_session_snapshot(session_id: str) -> dict | None:
    session = sessions.get_session(session_id)
    if session is None or session["is_archived"]:
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
    processing_statuses = {
        "processing",
        DocumentStage.uploaded,
        DocumentStage.parsing,
        DocumentStage.parsed,
        DocumentStage.chunked,
        DocumentStage.indexing,
    }
    if any(status in processing_statuses for status in statuses):
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
    return index_registry.get_store(session_id)


def destroy_session(session_id: str) -> None:
    sessions.archive_session(session_id)
    index_registry.discard_store(session_id)
    remove_session_dir(session_id)
