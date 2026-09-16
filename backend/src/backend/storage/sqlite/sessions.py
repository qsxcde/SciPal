import uuid
from datetime import UTC, datetime

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


def update_session_title(session_id: str, title: str) -> None:
    timestamp = now_iso()
    with transaction() as conn:
        conn.execute(
            "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
            (title, timestamp, session_id),
        )


def list_sessions(user_id: str | None = None) -> list[dict]:
    with connect() as conn:
        if user_id:
            rows = conn.execute(
                """
                SELECT
                  s.*,
                  (SELECT COUNT(*) FROM documents WHERE session_id = s.id) AS document_count,
                  (SELECT COUNT(*) FROM messages WHERE session_id = s.id) AS message_count,
                  (SELECT COUNT(*) FROM chunks WHERE session_id = s.id) AS indexed_chunks
                FROM sessions s
                WHERE s.is_archived = 0 AND s.user_id = ?
                ORDER BY s.is_pinned DESC, s.updated_at DESC
                """,
                (user_id,),
            ).fetchall()
        else:
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
