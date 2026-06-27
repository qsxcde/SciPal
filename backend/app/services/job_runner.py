import json
import logging
import threading
from pathlib import Path

from backend.domain.config import settings
from backend.domain.states import DocumentStage
from backend.domain.states import JobStatus
from backend.storage.sqlite import documents as document_repo
from backend.storage.sqlite import jobs as job_repo
from backend.app.services.ingestion_service import run_document_ingestion_job

logger = logging.getLogger(__name__)


class InProcessJobRunner:
    """Lightweight in-process worker for queued ingestion jobs."""

    def __init__(self) -> None:
        self._session_locks: dict[str, threading.Lock] = {}
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            logger.info("Job runner already running", extra=self.health_status())
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_forever,
            name="scipal-job-runner",
            daemon=True,
        )
        self._thread.start()
        logger.info("Started job runner", extra=self.health_status())

    def stop(self, timeout_seconds: float = 1.0) -> None:
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout_seconds)
            if self._thread.is_alive():
                logger.warning("Job runner did not stop before timeout", extra=self.health_status())
        self._thread = None
        logger.info("Stopped job runner", extra=self.health_status())

    def health_status(self) -> dict:
        thread = self._thread
        running = bool(thread is not None and thread.is_alive())
        return {
            "running": running,
            "thread_name": thread.name if thread is not None else None,
            "stop_requested": self._stop_event.is_set(),
        }

    def recover_interrupted_jobs(self) -> int:
        recovered = 0
        for job in job_repo.list_running_jobs():
            if job_repo.requeue_interrupted_job(job["id"]):
                recovered += 1
                logger.warning(
                    "Requeued interrupted ingestion job %s for session %s",
                    job["id"],
                    job["session_id"],
                )
        logger.info("Recovered %s interrupted ingestion jobs", recovered)
        return recovered

    def tick(self) -> int:
        jobs = job_repo.list_runnable_jobs(limit=1)
        if not jobs:
            return 0
        job = jobs[0]
        if not job_repo.mark_job_running(job["id"]):
            logger.info("Skipped ingestion job %s because it was no longer queued", job["id"])
            return 0
        logger.info(
            "Starting ingestion job %s for session %s document %s",
            job["id"],
            job["session_id"],
            job.get("document_id"),
        )
        self._run_job(job)
        return 1

    def _run_job(self, job: dict) -> None:
        session_lock = self._session_locks.setdefault(job["session_id"], threading.Lock())
        with session_lock:
            try:
                self._run_document_ingestion_job(job)
            except Exception as exc:
                logger.exception(
                    "Failed ingestion job %s for session %s document %s",
                    job["id"],
                    job["session_id"],
                    job.get("document_id"),
                )
                job_repo.mark_job_finished(job["id"], JobStatus.failed, str(exc))
            else:
                logger.info(
                    "Finished ingestion job %s for session %s document %s",
                    job["id"],
                    job["session_id"],
                    job.get("document_id"),
                )

    def _run_document_ingestion_job(self, job: dict) -> None:
        if job["type"] != "document_ingestion":
            raise RuntimeError(f"Unsupported job type: {job['type']}")
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

    def _run_forever(self) -> None:
        logger.info("Job runner loop started")
        while not self._stop_event.is_set():
            try:
                processed = self.tick()
            except Exception:
                logger.exception("Job runner tick failed")
                processed = 0
            if processed == 0:
                self._stop_event.wait(settings.runner_idle_poll_interval)
        logger.info("Job runner loop stopped")
