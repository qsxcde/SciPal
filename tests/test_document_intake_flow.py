"""Upload intake: validation, persistence and job enqueueing."""

import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from backend.app.services.document_service import intake_document_upload
from backend.domain.config import data_dir
from backend.domain.config import settings
from backend.storage.sqlite import jobs
from backend.storage.sqlite import sessions

PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"


def _create_session() -> dict:
    return sessions.create_session(settings.msg_default_session_title)


def _intake(session_id: str, **overrides) -> dict:
    kwargs = {
        "session_id": session_id,
        "filename": "attention.pdf",
        "mime_type": "application/pdf",
        "pdf_bytes": PDF_BYTES,
        "file_size": len(PDF_BYTES),
    }
    kwargs.update(overrides)
    return intake_document_upload(**kwargs)


@pytest.mark.integration
def test_upload_persists_file_document_and_queued_job():
    session = _create_session()

    result = _intake(session["id"])

    document = result["document"]
    job = result["job"]
    assert document["status"] == "uploaded"
    assert document["chunk_count"] == 0
    assert Path(document["file_path"]).read_bytes() == PDF_BYTES
    assert Path(document["file_path"]).is_relative_to(data_dir())

    assert job["status"] == "queued"
    assert job["stage"] == "uploaded"
    assert json.loads(job["payload_json"])["document_id"] == document["id"]
    assert sessions.get_session(session["id"])["title"] == "attention.pdf"


@pytest.mark.integration
def test_unknown_session_is_rejected_and_writes_nothing():
    with pytest.raises(HTTPException) as exc_info:
        _intake("missing-session")

    assert exc_info.value.status_code == 404
    assert not (data_dir() / "raw").exists()


@pytest.mark.integration
def test_oversized_upload_is_rejected_before_persisting():
    session = _create_session()

    with pytest.raises(HTTPException) as exc_info:
        _intake(session["id"], file_size=settings.upload_max_bytes + 1)

    assert exc_info.value.status_code == 413
    assert jobs.list_jobs_for_session(session["id"]) == []


@pytest.mark.integration
def test_non_pdf_payload_is_rejected():
    session = _create_session()

    with pytest.raises(HTTPException) as exc_info:
        _intake(session["id"], pdf_bytes=b"not a pdf", file_size=9)

    assert exc_info.value.status_code == 400
    assert jobs.list_jobs_for_session(session["id"]) == []
