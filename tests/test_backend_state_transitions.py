"""State transitions enforced by the SQLite repositories."""

import pytest

from backend.api.schemas.session import PersistedMessage
from backend.domain.states import DocumentStage, JobStatus, MessageStatus
from backend.storage.sqlite import documents
from backend.storage.sqlite import jobs
from backend.storage.sqlite import messages
from backend.storage.sqlite import sessions


def _new_job(session_id: str) -> dict:
    return jobs.create_job(
        session_id=session_id,
        document_id=None,
        job_type="document_ingestion",
        stage=DocumentStage.uploaded,
    )


@pytest.mark.unit
def test_job_cas_prevents_double_execution():
    session = sessions.create_session("state transitions")
    job = _new_job(session["id"])

    assert jobs.mark_job_running(job["id"]) is True
    assert jobs.mark_job_running(job["id"]) is False

    stored = jobs.get_job(job["id"])
    assert stored["status"] == JobStatus.running
    assert stored["attempt"] == 1


@pytest.mark.unit
def test_job_cannot_finish_before_running_or_twice():
    session = sessions.create_session("job finish")
    job = _new_job(session["id"])

    with pytest.raises(ValueError):
        jobs.mark_job_finished(job["id"], JobStatus.queued)  # type: ignore[arg-type]

    assert jobs.mark_job_finished(job["id"], JobStatus.succeeded) is False

    assert jobs.mark_job_running(job["id"]) is True
    assert jobs.mark_job_finished(job["id"], JobStatus.succeeded) is True
    assert jobs.mark_job_finished(job["id"], JobStatus.failed) is False

    stored = jobs.get_job(job["id"])
    assert stored["status"] == JobStatus.succeeded
    assert stored["finished_at"] is not None


@pytest.mark.unit
def test_document_status_update_clears_stale_error_message():
    session = sessions.create_session("document status")
    document = documents.create_document(
        session_id=session["id"],
        filename="paper.pdf",
        file_path="/tmp/paper.pdf",
        mime_type="application/pdf",
        file_size=1024,
    )
    assert document["status"] == DocumentStage.uploaded
    assert document["chunk_count"] == 0

    documents.update_document_status(
        document["id"], DocumentStage.failed, error_message="boom"
    )
    assert documents.get_document(document["id"])["error_message"] == "boom"

    documents.update_document_status(document["id"], DocumentStage.parsing)
    refreshed = documents.get_document(document["id"])
    assert refreshed["status"] == DocumentStage.parsing
    assert refreshed["error_message"] is None


@pytest.mark.unit
def test_stopped_message_satisfies_the_persisted_message_contract():
    """Regression: a stopped answer must not break GET /sessions/{id}.

    application/chat.py persists status="stopped" when the client aborts
    mid-stream. The snapshot response model is what turns such a row into a
    500 for the whole session, so the contract is asserted against the stored
    row rather than against a hand-built payload.
    """
    session = sessions.create_session("stopped answer")
    stored = messages.create_message(
        session_id=session["id"],
        role="assistant",
        content="partial answer",
        status=MessageStatus.stopped,
    )

    persisted = PersistedMessage(**stored)

    assert persisted.status is MessageStatus.stopped
    assert persisted.content == "partial answer"
