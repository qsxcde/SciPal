import uuid

from backend.storage.sqlite.connection import connect, transaction
from backend.storage.sqlite.jobs import get_job
from backend.storage.sqlite.schema import init_db
from backend.storage.sqlite.sessions import now_iso, touch_session


def create_document(
    session_id: str,
    filename: str,
    file_path: str,
    mime_type: str,
    file_size: int,
    document_id: str | None = None,
) -> dict:
    init_db()
    document_id = document_id or str(uuid.uuid4())
    timestamp = now_iso()
    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO documents (
              id, session_id, filename, file_path, mime_type, file_size,
              chunk_count, status, error_message, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 0, 'uploaded', NULL, ?, ?)
            """,
            (document_id, session_id, filename, file_path, mime_type, file_size, timestamp, timestamp),
        )
    touch_session(session_id)
    document = get_document(document_id)
    if document is None:
        raise RuntimeError("创建文档失败")
    return document


def get_document(document_id: str) -> dict | None:
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        return dict(row) if row else None


def list_documents(session_id: str) -> list[dict]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM documents WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def create_document_with_job(
    session_id: str,
    filename: str,
    file_path: str,
    mime_type: str,
    file_size: int,
    document_id: str | None = None,
    job_type: str = "document_ingestion",
    job_stage: str = "uploaded",
    job_payload_json: str | None = None,
) -> tuple[dict, dict]:
    """Create a document and its ingestion job in a single atomic transaction."""
    init_db()
    document_id = document_id or str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    timestamp = now_iso()
    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO documents (
              id, session_id, filename, file_path, mime_type, file_size,
              chunk_count, status, error_message, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 0, 'uploaded', NULL, ?, ?)
            """,
            (document_id, session_id, filename, file_path, mime_type, file_size, timestamp, timestamp),
        )
        conn.execute(
            """
            INSERT INTO jobs (
              id, session_id, document_id, type, status, stage, attempt,
              error_message, payload_json, created_at, started_at, finished_at
            )
            VALUES (?, ?, ?, ?, 'queued', ?, 0, NULL, ?, ?, NULL, NULL)
            """,
            (job_id, session_id, document_id, job_type, job_stage, job_payload_json, timestamp),
        )
    touch_session(session_id)
    document = get_document(document_id)
    job = get_job(job_id)
    if document is None:
        raise RuntimeError("创建文档失败")
    if job is None:
        raise RuntimeError("创建任务失败")
    return document, job


def delete_document(document_id: str) -> None:
    init_db()
    document = get_document(document_id)
    if document is None:
        return
    with transaction() as conn:
        conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
        conn.execute("DELETE FROM jobs WHERE document_id = ?", (document_id,))
        conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
    touch_session(document["session_id"])


def update_document_status(
    document_id: str,
    status: str,
    chunk_count: int | None = None,
    error_message: str | None = None,
) -> None:
    timestamp = now_iso()
    with transaction() as conn:
        conn.execute(
            """
            UPDATE documents
            SET status = ?,
                chunk_count = COALESCE(?, chunk_count),
                error_message = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (status, chunk_count, error_message, timestamp, document_id),
        )


def list_orphaned_uploaded_documents() -> list[dict]:
    """Find documents with status 'uploaded' that have no associated job."""
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT d.* FROM documents d
            LEFT JOIN jobs j ON j.document_id = d.id
            WHERE d.status = 'uploaded' AND j.id IS NULL
            """
        ).fetchall()
        return [dict(row) for row in rows]


def update_document_artifacts(
    document_id: str,
    parsed_ir_path: str | None,
    parsed_markdown_path: str | None,
    quality_report_path: str | None,
    parser_name: str | None,
    parser_version: str | None,
    parse_quality_status: str | None,
) -> None:
    init_db()
    timestamp = now_iso()
    with transaction() as conn:
        conn.execute(
            """
            UPDATE documents
            SET parsed_ir_path = ?,
                parsed_markdown_path = ?,
                quality_report_path = ?,
                parser_name = ?,
                parser_version = ?,
                parse_quality_status = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                parsed_ir_path,
                parsed_markdown_path,
                quality_report_path,
                parser_name,
                parser_version,
                parse_quality_status,
                timestamp,
                document_id,
            ),
        )
