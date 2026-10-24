"""Snapshot GC: only failed/stale snapshots may be removed."""

from pathlib import Path

import pytest

from backend.config import data_dir
from backend.scripts.gc_index_snapshots import collect_snapshots
from backend.storage.sqlite import index_snapshots
from backend.storage.sqlite import sessions


def _write_files(token: str) -> tuple[Path, Path]:
    directory = data_dir() / "index" / "snapshots"
    directory.mkdir(parents=True, exist_ok=True)
    index_path = directory / f"{token}.faiss.index"
    chunks_path = directory / f"{token}.chunks.json"
    index_path.write_text("index")
    chunks_path.write_text("[]")
    return index_path, chunks_path


def _create(session_id: str, token: str, index_path: Path, chunks_path: Path) -> dict:
    return index_snapshots.create_building_snapshot(
        session_id=session_id,
        index_path=str(index_path),
        chunks_path=str(chunks_path),
        document_ids=["doc-1"],
    )


@pytest.mark.integration
def test_collects_failed_and_stale_snapshots_but_keeps_ready():
    session_id = sessions.create_session("gc")["id"]

    stale_index, stale_chunks = _write_files("stale")
    stale = _create(session_id, "stale", stale_index, stale_chunks)
    assert index_snapshots.mark_snapshot_ready(stale["id"]) is True

    ready_index, ready_chunks = _write_files("ready")
    ready = _create(session_id, "ready", ready_index, ready_chunks)
    assert index_snapshots.mark_snapshot_ready(ready["id"]) is True

    failed_index, failed_chunks = _write_files("failed")
    failed = _create(session_id, "failed", failed_index, failed_chunks)
    assert index_snapshots.mark_snapshot_failed(failed["id"], "boom") is True

    summary = collect_snapshots(stale_days=0, apply=True)

    assert summary["candidates"] == 2
    assert summary["rows_deleted"] == 2
    assert not stale_index.exists()
    assert not stale_chunks.exists()
    assert not failed_index.exists()
    assert ready_index.exists()
    assert index_snapshots.get_snapshot(stale["id"]) is None
    assert index_snapshots.get_snapshot(failed["id"]) is None
    assert index_snapshots.get_snapshot(ready["id"])["status"] == "ready"


@pytest.mark.integration
def test_dry_run_reports_without_deleting():
    session_id = sessions.create_session("gc dry run")["id"]
    index_path, chunks_path = _write_files("failed")
    snapshot = _create(session_id, "failed", index_path, chunks_path)
    assert index_snapshots.mark_snapshot_failed(snapshot["id"], "boom") is True

    summary = collect_snapshots(stale_days=0, apply=False)

    assert summary["candidates"] == 1
    assert summary["files_deleted"] == 2
    assert summary["rows_deleted"] == 0
    assert index_path.exists()
    assert index_snapshots.get_snapshot(snapshot["id"]) is not None


@pytest.mark.integration
def test_snapshot_files_outside_data_dir_are_skipped(tmp_path):
    session_id = sessions.create_session("gc outside")["id"]
    outside_index = tmp_path / "outside.faiss.index"
    outside_chunks = tmp_path / "outside.chunks.json"
    outside_index.write_text("index")
    outside_chunks.write_text("[]")
    snapshot = _create(session_id, "outside", outside_index, outside_chunks)
    assert index_snapshots.mark_snapshot_failed(snapshot["id"], "boom") is True

    summary = collect_snapshots(stale_days=0, apply=True)

    assert summary["skipped_paths"] == 2
    assert outside_index.exists()
    assert outside_chunks.exists()
    assert index_snapshots.get_snapshot(snapshot["id"]) is None
