"""Ingestion failure: document, job, snapshot and files must stay consistent."""

import json
from pathlib import Path

import pytest

# The ingestion chain imports the RAG stack (faiss/torch/httpx); CI installs only
# the light dependency set, so skip there rather than failing collection.
pytest.importorskip("faiss", reason="faiss-cpu is not installed")
pytest.importorskip("torch", reason="torch is not installed")
pytest.importorskip("httpx", reason="httpx is not installed")

from backend.application import ingestion as ingestion_module
from backend.config import data_dir
from backend.domain.exceptions import PaperParseError
from backend.domain.states import DocumentStage
from backend.storage.sqlite import documents as document_repo
from backend.storage.sqlite import index_snapshots as snapshot_repo
from backend.storage.sqlite import jobs as job_repo
from backend.storage.sqlite import sessions
from backend.application.ingestion import run_queued_ingestion_job
from backend.worker.handlers import DOCUMENT_INGESTION_JOB
from backend.worker.runner import InProcessJobRunner, register_handler


def _seed(tmp_path: Path, *, create_file: bool = True) -> tuple[dict, dict, dict]:
    session = sessions.create_session("ingestion failure")
    pdf_path = tmp_path / "paper.pdf"
    if create_file:
        pdf_path.write_bytes(b"%PDF-1.7 fake")
    document = document_repo.create_document(
        session_id=session["id"],
        filename="paper.pdf",
        file_path=str(pdf_path),
        mime_type="application/pdf",
        file_size=12,
    )
    job = job_repo.create_job(
        session_id=session["id"],
        document_id=document["id"],
        job_type=DOCUMENT_INGESTION_JOB,
        stage=DocumentStage.uploaded,
        payload_json=json.dumps(
            {"document_id": document["id"], "file_path": str(pdf_path)}
        ),
    )
    return session, document, job


def _snapshot_files(session_id: str) -> list[Path]:
    root = data_dir() / "index" / session_id
    if not root.exists():
        return []
    return sorted(root.rglob("*.faiss.index"))


@pytest.mark.integration
def test_parse_failure_marks_document_job_and_snapshot_state(monkeypatch, tmp_path):
    register_handler(DOCUMENT_INGESTION_JOB, run_queued_ingestion_job)
    session, document, job = _seed(tmp_path)

    def _explode(**_kwargs):
        raise PaperParseError("parser exploded")

    monkeypatch.setattr(ingestion_module, "process_pdf_document", _explode)

    runner = InProcessJobRunner()
    assert runner.tick() == 1

    stored_document = document_repo.get_document(document["id"])
    assert stored_document["status"] == "failed"
    assert "parser exploded" in (stored_document["error_message"] or "")
    assert job_repo.get_job(job["id"])["status"] == "failed"

    assert snapshot_repo.get_active_ready_snapshot(session["id"]) is None
    assert _snapshot_files(session["id"]) == []


@pytest.mark.integration
def test_missing_upload_file_fails_before_parsing(monkeypatch, tmp_path):
    register_handler(DOCUMENT_INGESTION_JOB, run_queued_ingestion_job)
    _session, document, job = _seed(tmp_path, create_file=False)

    with pytest.raises(FileNotFoundError):
        run_queued_ingestion_job(job)

    stored_document = document_repo.get_document(document["id"])
    assert stored_document["status"] == "failed"
    assert stored_document["chunk_count"] == 0
    assert stored_document["error_message"]


@pytest.mark.integration
def test_failed_job_does_not_block_the_next_job_for_the_same_session(monkeypatch, tmp_path):
    register_handler(DOCUMENT_INGESTION_JOB, run_queued_ingestion_job)
    session, failed_document, failed_job = _seed(tmp_path)

    def _explode(**_kwargs):
        raise PaperParseError("parser exploded")

    monkeypatch.setattr(ingestion_module, "process_pdf_document", _explode)

    runner = InProcessJobRunner()
    assert runner.tick() == 1
    assert job_repo.get_job(failed_job["id"])["status"] == "failed"

    # 第二个任务仍然可以被取到，且失败态不会串到新文档上
    second = document_repo.create_document(
        session_id=session["id"],
        filename="second.pdf",
        file_path=str(tmp_path / "second.pdf"),
        mime_type="application/pdf",
        file_size=4,
    )
    job_repo.create_job(
        session_id=session["id"],
        document_id=second["id"],
        job_type=DOCUMENT_INGESTION_JOB,
        stage=DocumentStage.uploaded,
        payload_json=json.dumps({"document_id": second["id"]}),
    )

    assert runner.tick() == 1
    assert document_repo.get_document(second["id"])["status"] == "failed"
    assert document_repo.get_document(failed_document["id"])["status"] == "failed"
