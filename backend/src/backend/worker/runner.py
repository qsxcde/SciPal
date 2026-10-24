"""In-process worker: FIFO job consumption with a pluggable handler registry."""

import logging
import threading
from collections.abc import Callable

from backend.config import settings
from backend.domain.states import JobStatus
from backend.storage.sqlite import jobs as job_repo

logger = logging.getLogger(__name__)

JobHandler = Callable[[dict], None]

_handlers: dict[str, JobHandler] = {}
_handlers_lock = threading.Lock()


def register_handler(job_type: str, handler: JobHandler) -> None:
    """Register the handler responsible for one ``jobs.type`` value."""
    with _handlers_lock:
        _handlers[job_type] = handler


def get_handler(job_type: str) -> JobHandler | None:
    with _handlers_lock:
        return _handlers.get(job_type)


class InProcessJobRunner:
    """Lightweight in-process worker for queued jobs.

    The runner only knows about the job queue; what a job *does* comes from the
    handler registered for its type, so new job types never require touching
    this module.
    """

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
                    "Requeued interrupted job %s (type=%s) for session %s",
                    job["id"], job.get("type"), job["session_id"],
                )
        logger.info("Recovered %s interrupted jobs", recovered)
        return recovered

    def tick(self) -> int:
        jobs = job_repo.list_runnable_jobs(limit=1)
        if not jobs:
            return 0
        job = jobs[0]
        if not job_repo.mark_job_running(job["id"]):
            logger.info("Skipped job %s because it was no longer queued", job["id"])
            return 0
        logger.info(
            "Starting job %s type=%s for session %s document %s",
            job["id"], job.get("type"), job["session_id"], job.get("document_id"),
        )
        self._run_job(job)
        return 1

    def _run_job(self, job: dict) -> None:
        session_lock = self._session_locks.setdefault(job["session_id"], threading.Lock())
        with session_lock:
            try:
                self._execute_job(job)
            except Exception as exc:
                logger.exception(
                    "Failed job %s type=%s for session %s document %s",
                    job["id"], job.get("type"), job["session_id"], job.get("document_id"),
                )
                job_repo.mark_job_finished(job["id"], JobStatus.failed, str(exc))
            else:
                logger.info(
                    "Finished job %s type=%s for session %s document %s",
                    job["id"], job.get("type"), job["session_id"], job.get("document_id"),
                )

    def _execute_job(self, job: dict) -> None:
        job_type = job.get("type")
        handler = get_handler(job_type) if job_type else None
        if handler is None:
            raise RuntimeError(f"Unsupported job type: {job_type}")
        handler(job)

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
