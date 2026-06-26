import uuid

from backend.storage.sqlite.connection import connect, transaction
from backend.storage.sqlite.schema import init_db
from backend.storage.sqlite.sessions import now_iso


def upsert_index(session_id: str, index_path: str, chunks_path: str, status: str) -> dict:
    init_db()
    timestamp = now_iso()
    existing = get_index(session_id)
    with transaction() as conn:
        if existing:
            conn.execute(
                """
                UPDATE retrieval_indexes
                SET index_path = ?, chunks_path = ?, status = ?, updated_at = ?
                WHERE session_id = ?
                """,
                (index_path, chunks_path, status, timestamp, session_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO retrieval_indexes (id, session_id, index_path, chunks_path, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), session_id, index_path, chunks_path, status, timestamp),
            )
    index = get_index(session_id)
    if index is None:
        raise RuntimeError("保存索引元数据失败")
    return index


def get_index(session_id: str) -> dict | None:
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM retrieval_indexes WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return dict(row) if row else None
