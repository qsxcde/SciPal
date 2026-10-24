"""Job handlers: translate a queued job row into an application use case call."""

import json
import logging
from pathlib import Path

from backend.application.ingestion import run_document_ingestion_job
from backend.domain.states import DocumentStage, JobStatus
from backend.storage.sqlite import documents as document_repo
from backend.storage.sqlite import jobs as job_repo
from backend.worker.runner import register_handler

logger = logging.getLogger(__name__)

DOCUMENT_INGESTION_JOB = "document_ingestion"


def ingest_document(job: dict) -> None:
    if job["stage"] != DocumentStage.uploaded:
        raise RuntimeError(f"Unsupported job stage: {job['stage']}")
    payload = json.loads(job["payload_json"] or "{}")
    document_id = payload.get("document_id") or job["document_id"]
    if document_id is None:
        raise RuntimeError("Missing document id in job payload")
    document = document_repo.get_document(document_id)
    if document is None:
        raise RuntimeError("Document not found for ingestion job")
    file_path = payload.get("file_path") or document["file_path"]
    try:
        pdf_bytes = Path(file_path).read_bytes()
    except Exception as exc:
        document_repo.update_document_status(
            document_id,
            DocumentStage.failed,
            chunk_count=0,
            error_message=str(exc),
        )
        raise
    run_document_ingestion_job(
        session_id=job["session_id"],
        document=document,
        pdf_bytes=pdf_bytes,
    )
    job_repo.mark_job_finished(job["id"], JobStatus.succeeded)


def register_default_handlers() -> None:
    register_handler(DOCUMENT_INGESTION_JOB, ingest_document)
