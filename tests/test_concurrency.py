"""Concurrency invariants that the refactor must not break.

SQLite runs in WAL mode with a 5s busy timeout, so these tests also act as a
smoke test for the connection settings under real threads.
"""

import threading
from pathlib import Path

import pytest

from backend.application.documents import intake_document_upload
from backend.domain.states import DocumentStage
from backend.storage.sqlite import documents as document_repo
from backend.storage.sqlite import index_snapshots as snapshot_repo
from backend.storage.sqlite import jobs as job_repo
from backend.storage.sqlite import sessions
from backend.worker.runner import InProcessJobRunner, register_handler

PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"


def _snapshot(session_id: str, token: str) -> dict:
    return snapshot_repo.create_building_snapshot(
        session_id=session_id,
        index_path=f"snapshots/{token}.faiss.index",
        chunks_path=f"snapshots/{token}.chunks.json",
        document_ids=["doc-1"],
    )


@pytest.mark.integration
def test_concurrent_promotions_leave_exactly_one_ready_snapshot():
    session_id = sessions.create_session("concurrent promote")["id"]
    first = _snapshot(session_id, "a")
    second = _snapshot(session_id, "b")
    barrier = threading.Barrier(2)
    results: dict[str, bool] = {}

    def _promote(snapshot: dict) -> None:
        barrier.wait()
        results[snapshot["id"]] = snapshot_repo.mark_snapshot_ready(snapshot["id"])

    threads = [
        threading.Thread(target=_promote, args=(snapshot,))
        for snapshot in (first, second)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    # 两次晋升都会被接受（后一次覆盖前一次），但任何时刻都不允许出现两个 ready
    assert all(results.values())
    statuses = sorted(snapshot_repo.get_snapshot(s["id"])["status"] for s in (first, second))
    assert statuses == ["ready", "stale"]
    assert snapshot_repo.get_active_ready_snapshot(session_id) is not None


@pytest.mark.integration
def test_the_same_job_cannot_be_claimed_twice():
    session_id = sessions.create_session("job claim")["id"]
    job = job_repo.create_job(
        session_id=session_id,
        document_id=None,
        job_type="counting_job",
        stage=DocumentStage.uploaded,
    )
    seen: list[str] = []
    lock = threading.Lock()

    def _handler(claimed: dict) -> None:
        with lock:
            seen.append(claimed["id"])

    register_handler("counting_job", _handler)
    runner = InProcessJobRunner()
    barrier = threading.Barrier(4)

    def _tick() -> None:
        barrier.wait()
        runner.tick()

    threads = [threading.Thread(target=_tick) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert seen == [job["id"]]
    assert job_repo.get_job(job["id"])["status"] == "running"


@pytest.mark.integration
def test_concurrent_uploads_create_independent_documents(tmp_path: Path):
    session_id = sessions.create_session("concurrent upload")["id"]
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def _upload(index: int) -> None:
        barrier.wait()
        try:
            intake_document_upload(
                session_id=session_id,
                filename=f"paper-{index}.pdf",
                mime_type="application/pdf",
                pdf_bytes=PDF_BYTES + str(index).encode(),
                file_size=len(PDF_BYTES) + 1,
            )
        except BaseException as exc:  # noqa: BLE001 - surfaced by the assertion below
            errors.append(exc)

    threads = [threading.Thread(target=_upload, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    stored = document_repo.list_documents(session_id)
    assert len(stored) == 2
    assert len({document["file_path"] for document in stored}) == 2


@pytest.mark.integration
def test_two_sessions_can_ingest_in_parallel():
    """max_workers>1：慢任务不再独占整个队列。"""
    first_session = sessions.create_session("parallel a")["id"]
    second_session = sessions.create_session("parallel b")["id"]
    for session_id in (first_session, second_session):
        job_repo.create_job(
            session_id=session_id,
            document_id=None,
            job_type="parallel_job",
            stage=DocumentStage.uploaded,
        )

    # 两个 handler 必须同时到达栅栏，串行执行会超时并判失败
    barrier = threading.Barrier(2, timeout=5)

    def _handler(_job: dict) -> None:
        barrier.wait()

    register_handler("parallel_job", _handler)
    runner = InProcessJobRunner(max_workers=2)
    try:
        assert runner.tick() == 2
        assert runner.wait_idle(timeout=5) is True
        assert barrier.n_waiting == 0
    finally:
        runner.stop()
