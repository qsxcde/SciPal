import uuid
from datetime import UTC, datetime

from backend.domain.states import DocumentStage
from backend.domain.states import SessionStatus
from backend.storage.sqlite.connection import connect, transaction
def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def create_session(title: str, user_id: str | None = None) -> dict:
    session_id = str(uuid.uuid4())
    timestamp = now_iso()
    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO sessions (id, title, user_id, created_at, updated_at, last_opened_at, is_archived)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (session_id, title, user_id, timestamp, timestamp, timestamp),
        )
    session = get_session(session_id)
    if session is None:
        raise RuntimeError("创建会话失败")
    return session


def get_session(session_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return dict(row) if row else None


def touch_session(session_id: str) -> None:
    timestamp = now_iso()
    with transaction() as conn:
        conn.execute(
            "UPDATE sessions SET updated_at = ?, last_opened_at = ? WHERE id = ?",
            (timestamp, timestamp, session_id),
        )


def restore_session_timestamps(session_id: str, updated_at: str, last_opened_at: str) -> None:
    with transaction() as conn:
        conn.execute(
            "UPDATE sessions SET updated_at = ?, last_opened_at = ? WHERE id = ?",
            (updated_at, last_opened_at, session_id),
        )


def update_session_title(session_id: str, title: str) -> None:
    timestamp = now_iso()
    with transaction() as conn:
        conn.execute(
            "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
            (title, timestamp, session_id),
        )


def list_sessions() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
              s.*,
              (SELECT COUNT(*) FROM documents WHERE session_id = s.id) AS document_count,
              (SELECT COUNT(*) FROM messages WHERE session_id = s.id) AS message_count,
              (SELECT COUNT(*) FROM chunks WHERE session_id = s.id) AS indexed_chunks
            FROM sessions s
            WHERE s.is_archived = 0
            ORDER BY s.is_pinned DESC, s.updated_at DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]


def get_session_snapshot(session_id: str) -> dict | None:
    from backend.storage.sqlite import chunks
    from backend.storage.sqlite import documents
    from backend.storage.sqlite import index_snapshots
    from backend.storage.sqlite import indexes
    from backend.storage.sqlite import jobs
    from backend.storage.sqlite import messages

    session = get_session(session_id)
    if session is None or session["is_archived"]:
        return None
    session_documents = documents.list_documents(session_id)
    session_messages = messages.list_messages(session_id)
    return build_session_snapshot(
        session={
            **session,
            "status": derive_session_status_from_documents(session_documents),
        },
        documents=session_documents,
        messages=session_messages,
        indexed_chunks=chunks.count_chunks(session_id),
        retrieval_index=indexes.get_index(session_id),
        active_index=index_snapshots.get_active_ready_snapshot(session_id),
        jobs=jobs.list_jobs_for_session(session_id),
    )


def derive_session_status(session_id: str) -> str:
    from backend.storage.sqlite import documents

    session_documents = documents.list_documents(session_id)
    return derive_session_status_from_documents(session_documents)


def derive_session_status_from_documents(session_documents: list[dict]) -> str:
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


def build_session_snapshot(
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
    snapshot["status"] = session.get("status") or derive_session_status_from_documents(documents)
    return snapshot


def archive_session(session_id: str) -> None:
    with transaction() as conn:
        conn.execute(
            "UPDATE sessions SET is_archived = 1, updated_at = ? WHERE id = ?",
            (now_iso(), session_id),
        )


def update_session(session_id: str, title: str | None = None, is_pinned: bool | None = None) -> dict | None:
    session = get_session(session_id)
    if session is None:
        return None
    next_title = title if title is not None else session["title"]
    next_is_pinned = int(is_pinned) if is_pinned is not None else session["is_pinned"]
    timestamp = now_iso()
    with transaction() as conn:
        conn.execute(
            """
            UPDATE sessions
            SET title = ?, is_pinned = ?, updated_at = ?
            WHERE id = ?
            """,
            (next_title, next_is_pinned, timestamp, session_id),
        )
    return get_session_summary(session_id)


def get_session_summary(session_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT
              s.*,
              (SELECT COUNT(*) FROM documents WHERE session_id = s.id) AS document_count,
              (SELECT COUNT(*) FROM messages WHERE session_id = s.id) AS message_count,
              (SELECT COUNT(*) FROM chunks WHERE session_id = s.id) AS indexed_chunks
            FROM sessions s
            WHERE s.id = ? AND s.is_archived = 0
            """,
            (session_id,),
        ).fetchone()
        return dict(row) if row else None
