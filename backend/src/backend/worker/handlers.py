"""Job handlers: bind a job type to its application use case."""

from backend.application.ingestion import run_queued_ingestion_job
from backend.worker.runner import register_handler

DOCUMENT_INGESTION_JOB = "document_ingestion"


def register_default_handlers() -> None:
    register_handler(DOCUMENT_INGESTION_JOB, run_queued_ingestion_job)
