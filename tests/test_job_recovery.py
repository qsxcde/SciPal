"""Startup recovery: interrupted jobs must be re-queued, not lost."""

import pytest

from backend.domain.states import DocumentStage, JobStatus
from backend.storage.sqlite import jobs
from backend.storage.sqlite import sessions


@pytest.mark.unit
def test_running_job_is_requeued_and_attempt_is_preserved():
    session = sessions.create_session("recovery")
    job = jobs.create_job(
        session_id=session["id"],
        document_id=None,
        job_type="document_ingestion",
        stage=DocumentStage.uploaded,
    )
    assert jobs.mark_job_running(job["id"]) is True

    assert jobs.requeue_interrupted_job(job["id"]) is True

    stored = jobs.get_job(job["id"])
    assert stored["status"] == JobStatus.queued
    assert stored["attempt"] == 1
    assert stored["started_at"] is None
    assert stored["finished_at"] is None
    assert stored["error_message"] is None


@pytest.mark.unit
def test_requeue_is_a_noop_for_queued_jobs():
    session = sessions.create_session("recovery noop")
    job = jobs.create_job(
        session_id=session["id"],
        document_id=None,
        job_type="document_ingestion",
        stage=DocumentStage.uploaded,
    )

    assert jobs.requeue_interrupted_job(job["id"]) is False
    assert jobs.get_job(job["id"])["status"] == JobStatus.queued
