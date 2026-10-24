"""Index snapshot promotion and rollback semantics."""

import pytest

from backend.storage.sqlite import index_snapshots
from backend.storage.sqlite import sessions


def _create_snapshot(session_id: str, token: str, document_ids: list[str]) -> dict:
    return index_snapshots.create_building_snapshot(
        session_id=session_id,
        index_path=f"snapshots/{token}.faiss.index",
        chunks_path=f"snapshots/{token}.chunks.json",
        document_ids=document_ids,
    )


@pytest.mark.unit
def test_promotion_marks_previous_ready_snapshot_stale():
    session_id = sessions.create_session("snapshots")["id"]
    first = _create_snapshot(session_id, "first", ["doc-1"])
    assert index_snapshots.mark_snapshot_ready(first["id"]) is True

    second = _create_snapshot(session_id, "second", ["doc-1", "doc-2"])
    assert index_snapshots.mark_snapshot_ready(second["id"]) is True

    assert index_snapshots.get_snapshot(first["id"])["status"] == "stale"

    active = index_snapshots.get_active_ready_snapshot(session_id)
    assert active is not None
    assert active["id"] == second["id"]
    assert active["document_ids"] == ["doc-1", "doc-2"]


@pytest.mark.unit
def test_ready_snapshot_cannot_be_promoted_twice():
    session_id = sessions.create_session("double promote")["id"]
    snapshot = _create_snapshot(session_id, "only", ["doc-1"])

    assert index_snapshots.mark_snapshot_ready(snapshot["id"]) is True
    assert index_snapshots.mark_snapshot_ready(snapshot["id"]) is False
    assert index_snapshots.get_snapshot(snapshot["id"])["status"] == "ready"


@pytest.mark.unit
def test_rollback_restores_previous_ready_snapshot():
    session_id = sessions.create_session("rollback")["id"]
    previous = _create_snapshot(session_id, "previous", ["doc-1"])
    assert index_snapshots.mark_snapshot_ready(previous["id"]) is True

    promoted = _create_snapshot(session_id, "promoted", ["doc-1", "doc-2"])
    assert index_snapshots.mark_snapshot_ready(promoted["id"]) is True

    assert (
        index_snapshots.rollback_snapshot_promotion(
            promoted["id"], previous["id"], "metadata publish failed"
        )
        is True
    )

    rolled_back = index_snapshots.get_snapshot(promoted["id"])
    assert rolled_back["status"] == "failed"
    assert rolled_back["error_message"] == "metadata publish failed"
    assert index_snapshots.get_snapshot(previous["id"])["status"] == "ready"

    active = index_snapshots.get_active_ready_snapshot(session_id)
    assert active is not None
    assert active["id"] == previous["id"]


@pytest.mark.unit
def test_failed_building_snapshot_is_never_active():
    session_id = sessions.create_session("failed candidate")["id"]
    snapshot = _create_snapshot(session_id, "broken", ["doc-1"])

    assert index_snapshots.mark_snapshot_failed(snapshot["id"], "disk full") is True
    assert index_snapshots.get_active_ready_snapshot(session_id) is None
    assert index_snapshots.mark_snapshot_ready(snapshot["id"]) is False
