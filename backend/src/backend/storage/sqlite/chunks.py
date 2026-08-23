import json
import uuid

from backend.rag.ingestion.metadata import Chunk, ChunkMetadata
from backend.storage.sqlite.connection import connect, transaction
from backend.storage.sqlite.sessions import now_iso


def insert_chunks(session_id: str, document_id: str, parsed_chunks: list[Chunk]) -> None:
    if not parsed_chunks:
        return

    timestamp = now_iso()
    with transaction() as conn:
        conn.executemany(
            """
            INSERT INTO chunks (
              id, session_id, document_id, section, chunk_index,
              text_excerpt, text_content, type, section_path_json,
              page_start, page_end, bbox_json, block_ids_json,
              block_types_json, linked_block_ids_json, confidence,
              created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    str(uuid.uuid4()),
                    session_id,
                    document_id,
                    chunk.metadata.section,
                    chunk.metadata.chunk_index,
                    chunk.text[:240],
                    chunk.text,
                    chunk.metadata.type,
                    _json_or_none(chunk.metadata.section_path),
                    chunk.metadata.page_start,
                    chunk.metadata.page_end,
                    _json_or_none(chunk.metadata.bbox),
                    _json_or_none(chunk.metadata.block_ids),
                    _json_or_none(chunk.metadata.block_types),
                    _json_or_none(chunk.metadata.linked_block_ids),
                    chunk.metadata.confidence,
                    timestamp,
                )
                for chunk in parsed_chunks
            ],
        )
        conn.execute(
            """
            UPDATE documents
            SET chunk_count = (
              SELECT COUNT(*) FROM chunks WHERE document_id = ?
            ),
            updated_at = ?
            WHERE id = ?
            """,
            (document_id, timestamp, document_id),
        )


def _row_to_chunk(row: dict) -> Chunk:
    return Chunk(
        text=row["text_content"],
        metadata=ChunkMetadata(
            paper_id=row["document_id"],
            section=row["section"],
            chunk_index=row["chunk_index"],
            type=row["type"],
            section_path=_json_load(row["section_path_json"]),
            page_start=row["page_start"],
            page_end=row["page_end"],
            bbox=_json_load(row["bbox_json"]),
            block_ids=_json_load(row["block_ids_json"]),
            block_types=_json_load(row["block_types_json"]),
            linked_block_ids=_json_load(row["linked_block_ids_json"]),
            confidence=row["confidence"],
        ),
    )


def list_chunks(session_id: str) -> list[Chunk]:

    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM chunks WHERE session_id = ? ORDER BY created_at ASC, chunk_index ASC",
            (session_id,),
        ).fetchall()
    return [_row_to_chunk(row) for row in rows]


def list_chunks_for_documents(session_id: str, document_ids: list[str]) -> list[Chunk]:
    if not document_ids:
        return []

    placeholders = ", ".join("?" for _ in document_ids)
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM chunks
            WHERE session_id = ? AND document_id IN ({placeholders})
            ORDER BY created_at ASC, chunk_index ASC
            """,
            (session_id, *document_ids),
        ).fetchall()
    return [_row_to_chunk(row) for row in rows]


def list_chunk_document_ids(session_id: str) -> list[str]:

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT document_id, MIN(created_at) AS first_seen_at
            FROM chunks
            WHERE session_id = ?
            GROUP BY document_id
            ORDER BY first_seen_at ASC
            """,
            (session_id,),
        ).fetchall()
    return [str(row["document_id"]) for row in rows]


def delete_chunks_for_document(document_id: str) -> None:

    timestamp = now_iso()
    with transaction() as conn:
        conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
        conn.execute(
            """
            UPDATE documents
            SET chunk_count = 0,
                updated_at = ?
            WHERE id = ?
            """,
            (timestamp, document_id),
        )


def count_chunks(session_id: str) -> int:

    with connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS total FROM chunks WHERE session_id = ?", (session_id,)).fetchone()
        return int(row["total"])


def _json_or_none(value: object) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _json_load(value: str | None) -> object:
    if value is None:
        return None
    return json.loads(value)
