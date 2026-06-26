import uuid
from typing import Literal

from backend.domain.states import DocumentStage
from backend.domain.states import JobStatus
from backend.domain.states import TERMINAL_JOB_STATUSES
from backend.storage.sqlite.connection import connect
from backend.storage.sqlite.connection import row_to_dict
from backend.storage.sqlite.connection import transaction
from backend.storage.sqlite.schema import init_db
from backend.storage.sqlite.sessions import now_iso


def create_job(
    session_id: str,
    document_id: str | None,
    job_type: str,
    stage: DocumentStage,
    payload_json: str | None = None,
) -> dict:
    init_db()
    job_id = str(uuid.uuid4())
    timestamp = now_iso()
    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO jobs (
              id, session_id, document_id, type, status, stage, attempt,
              error_message, payload_json, created_at, started_at, finished_at
            )
            VALUES (?, ?, ?, ?, 'queued', ?, 0, NULL, ?, ?, NULL, NULL)
            """,
            (job_id, session_id, document_id, job_type, stage, payload_json, timestamp),
        )
    job = get_job(job_id)
    if job is None:
        raise RuntimeError("创建任务失败")
    return job


def list_runnable_jobs(limit: int = 10) -> list[dict]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM jobs
            WHERE status = 'queued'
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def list_running_jobs(limit: int = 10) -> list[dict]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM jobs
            WHERE status IN (?, ?)
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (JobStatus.running, JobStatus.interrupted, limit),
        ).fetchall()
        return [dict(row) for row in rows]


def list_jobs_for_session(session_id: str) -> list[dict]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM jobs
            WHERE session_id = ?
            ORDER BY created_at ASC
            """,
            (session_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def mark_job_running(job_id: str) -> bool:
    init_db()
    with transaction() as conn:
        cursor = conn.execute(
            """
            UPDATE jobs
            SET status = 'running',
                attempt = attempt + 1,
                error_message = NULL,
                started_at = ?,
                finished_at = NULL
            WHERE id = ? AND status = 'queued'
            """,
            (now_iso(), job_id),
        )
    return cursor.rowcount > 0


def requeue_interrupted_job(job_id: str) -> bool:
    init_db()
    with transaction() as conn:
        cursor = conn.execute(
            """
            UPDATE jobs
            SET status = ?,
                error_message = NULL,
                started_at = NULL,
                finished_at = NULL
            WHERE id = ? AND status IN (?, ?)
            """,
            (
                JobStatus.queued,
                job_id,
                JobStatus.running,
                JobStatus.interrupted,
            ),
        )
    return cursor.rowcount > 0


def mark_job_finished(
    job_id: str,
    status: Literal[
        JobStatus.succeeded,
        JobStatus.failed,
        JobStatus.cancelled,
        JobStatus.interrupted,
    ],
    error_message: str | None = None,
) -> bool:
    if status not in TERMINAL_JOB_STATUSES:
        raise ValueError("任务只能以终态结束")
    init_db()
    with transaction() as conn:
        cursor = conn.execute(
            """
            UPDATE jobs
            SET status = ?,
                error_message = ?,
                finished_at = ?
            WHERE id = ? AND status = ?
            """,
            (status, error_message, now_iso(), job_id, JobStatus.running),
        )
    return cursor.rowcount > 0


def get_job(job_id: str) -> dict | None:
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return row_to_dict(row)
