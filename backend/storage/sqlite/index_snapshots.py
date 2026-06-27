import json
import uuid

from backend.domain.states import IndexSnapshotStatus
from backend.storage.sqlite.connection import connect
from backend.storage.sqlite.connection import row_to_dict
from backend.storage.sqlite.connection import transaction
from backend.storage.sqlite.sessions import now_iso


def create_building_snapshot(
    session_id: str,
    index_path: str,
    chunks_path: str,
    document_ids: list[str],
) -> dict:

    snapshot_id = str(uuid.uuid4())
    timestamp = now_iso()
    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO index_snapshots (
              id, session_id, status, index_path, chunks_path, document_ids_json,
              error_message, created_at, updated_at
            )
            VALUES (?, ?, 'building', ?, ?, ?, NULL, ?, ?)
            """,
            (
                snapshot_id,
                session_id,
                index_path,
                chunks_path,
                json.dumps(document_ids, ensure_ascii=False),
                timestamp,
                timestamp,
            ),
        )
    snapshot = get_snapshot(snapshot_id)
    if snapshot is None:
        raise RuntimeError("创建索引快照失败")
    return snapshot


def mark_snapshot_ready(snapshot_id: str) -> bool:

    timestamp = now_iso()
    with transaction() as conn:
        target_snapshot = conn.execute(
            """
            SELECT session_id
            FROM index_snapshots
            WHERE id = ? AND status = ?
            """,
            (snapshot_id, IndexSnapshotStatus.building),
        ).fetchone()
        if target_snapshot is None:
            return False
        conn.execute(
            """
            UPDATE index_snapshots
            SET status = ?,
                updated_at = ?
            WHERE session_id = ? AND id != ? AND status = ?
            """,
            (
                IndexSnapshotStatus.stale,
                timestamp,
                target_snapshot["session_id"],
                snapshot_id,
                IndexSnapshotStatus.ready,
            ),
        )
        cursor = conn.execute(
            """
            UPDATE index_snapshots
            SET status = ?,
                error_message = NULL,
                updated_at = ?
            WHERE id = ? AND status = ?
            """,
            (
                IndexSnapshotStatus.ready,
                timestamp,
                snapshot_id,
                IndexSnapshotStatus.building,
            ),
        )
    return cursor.rowcount > 0


def mark_snapshot_failed(snapshot_id: str, error_message: str) -> bool:

    with transaction() as conn:
        cursor = conn.execute(
            """
            UPDATE index_snapshots
            SET status = ?,
                error_message = ?,
                updated_at = ?
            WHERE id = ? AND status = ?
            """,
            (
                IndexSnapshotStatus.failed,
                error_message,
                now_iso(),
                snapshot_id,
                IndexSnapshotStatus.building,
            ),
        )
    return cursor.rowcount > 0


def rollback_snapshot_promotion(
    snapshot_id: str,
    previous_ready_snapshot_id: str | None,
    error_message: str,
) -> bool:

    timestamp = now_iso()
    with transaction() as conn:
        if previous_ready_snapshot_id is not None:
            conn.execute(
                """
                UPDATE index_snapshots
                SET status = ?,
                    error_message = NULL,
                    updated_at = ?
                WHERE id = ? AND status = ?
                """,
                (
                    IndexSnapshotStatus.ready,
                    timestamp,
                    previous_ready_snapshot_id,
                    IndexSnapshotStatus.stale,
                ),
            )
        cursor = conn.execute(
            """
            UPDATE index_snapshots
            SET status = ?,
                error_message = ?,
                updated_at = ?
            WHERE id = ? AND status = ?
            """,
            (
                IndexSnapshotStatus.failed,
                error_message,
                timestamp,
                snapshot_id,
                IndexSnapshotStatus.ready,
            ),
        )
    return cursor.rowcount > 0


def get_active_ready_snapshot(session_id: str) -> dict | None:

    with connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM index_snapshots
            WHERE session_id = ? AND status = 'ready'
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
        return _row_to_snapshot(row)


def get_snapshot(snapshot_id: str) -> dict | None:

    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM index_snapshots WHERE id = ?",
            (snapshot_id,),
        ).fetchone()
        return _row_to_snapshot(row)


def _row_to_snapshot(row) -> dict | None:
    snapshot = row_to_dict(row)
    if snapshot is None:
        return None
    snapshot["document_ids"] = json.loads(snapshot.pop("document_ids_json"))
    return snapshot
