import logging
import time
import uuid
from pathlib import Path

from backend.storage.sqlite import chunks as chunk_repo
from backend.storage.sqlite import documents as document_repo
from backend.storage.sqlite import index_snapshots as snapshot_repo
from backend.storage.sqlite import indexes as index_repo
from backend.rag.indexing.vector_store import FAISSVectorStore
from backend.storage.vector_db.registry import discard_store
from backend.storage.paths import session_indexes_dir
from backend.rag.retrieval.filters import filter_indexable_chunks

logger = logging.getLogger(__name__)


def build_candidate_snapshot(session_id: str, document_id: str, pdf_bytes: bytes) -> dict:
    """Build and persist a candidate index snapshot without promoting it."""
    _ = pdf_bytes
    start = time.monotonic()
    candidate_token = str(uuid.uuid4())
    index_path = _snapshot_index_path(session_id, candidate_token)
    chunks_path = _snapshot_chunks_path(session_id, candidate_token)
    logger.info(
        "Building candidate index snapshot session_id=%s document_id=%s token=%s index_path=%s chunks_path=%s",
        session_id,
        document_id,
        candidate_token,
        index_path,
        chunks_path,
    )
    document_ids = chunk_repo.list_chunk_document_ids(session_id)
    if document_id not in document_ids:
        document_ids.append(document_id)
    snapshot = snapshot_repo.create_building_snapshot(
        session_id=session_id,
        index_path=str(index_path),
        chunks_path=str(chunks_path),
        document_ids=document_ids,
    )
    try:
        previous_ready = snapshot_repo.get_active_ready_snapshot(session_id)
        if previous_ready is not None:
            store = FAISSVectorStore.load(
                index_path=Path(previous_ready["index_path"]),
                chunks_path=Path(previous_ready["chunks_path"]),
            )
            logger.info(
                "Loaded previous ready snapshot %s with %d vectors for session_id=%s",
                previous_ready["id"],
                store._index.ntotal,
                session_id,
            )
        else:
            store = FAISSVectorStore()

        source_chunks = chunk_repo.list_chunks_for_documents(session_id, document_ids)

        if previous_ready is not None:
            existing_doc_ids = set(previous_ready["document_ids"])
            new_chunks = [c for c in source_chunks if c.metadata.paper_id not in existing_doc_ids]
            indexable_new = filter_indexable_chunks(new_chunks)
            skipped_count = len(source_chunks) - len(new_chunks)
            logger.info(
                "Loaded %d chunks for candidate snapshot session_id=%s snapshot_id=%s "
                "documents=%d (skipped %d already-indexed chunks from %d docs)",
                len(source_chunks),
                session_id,
                snapshot["id"],
                len(document_ids),
                skipped_count,
                len(existing_doc_ids),
            )
        else:
            indexable_new = filter_indexable_chunks(source_chunks)
            logger.info(
                "Loaded %d chunks for candidate snapshot session_id=%s snapshot_id=%s documents=%d",
                len(source_chunks),
                session_id,
                snapshot["id"],
                len(document_ids),
            )

        logger.info(
            "Indexing %d new chunks for candidate snapshot session_id=%s snapshot_id=%s",
            len(indexable_new),
            session_id,
            snapshot["id"],
        )
        store.add_chunks(indexable_new)
        store.save(index_path=index_path, chunks_path=chunks_path)
    except Exception as exc:
        logger.exception(
            "Failed candidate index snapshot session_id=%s snapshot_id=%s document_id=%s",
            session_id,
            snapshot["id"],
            document_id,
        )
        setattr(exc, "candidate_snapshot", snapshot)
        raise
    logger.info(
        "Saved candidate index snapshot session_id=%s snapshot_id=%s chunks=%d index_path=%s chunks_path=%s elapsed=%.2fs",
        session_id,
        snapshot["id"],
        len(indexable_new),
        index_path,
        chunks_path,
        time.monotonic() - start,
    )
    return snapshot


def commit_ready_snapshot(
    session_id: str,
    snapshot_id: str,
    document_id: str,
    chunk_count: int,
) -> dict:
    """Promote a successfully built candidate snapshot to the active ready snapshot."""
    start = time.monotonic()
    logger.info(
        "Committing ready index snapshot session_id=%s snapshot_id=%s document_id=%s chunk_count=%d",
        session_id,
        snapshot_id,
        document_id,
        chunk_count,
    )
    snapshot = snapshot_repo.get_snapshot(snapshot_id)
    if snapshot is None or snapshot["session_id"] != session_id:
        raise RuntimeError("索引快照不存在")
    if document_id not in snapshot["document_ids"]:
        raise RuntimeError("索引快照未包含目标文档")
    previous_ready_snapshot = snapshot_repo.get_active_ready_snapshot(session_id)
    previous_index_metadata = index_repo.get_index(session_id)
    if not snapshot_repo.mark_snapshot_ready(snapshot_id):
        raise RuntimeError("索引快照无法切换为 ready")
    ready_snapshot = snapshot_repo.get_snapshot(snapshot_id)
    if ready_snapshot is None:
        raise RuntimeError("索引快照切换后不可用")
    metadata_published = False
    try:
        index_repo.upsert_index(
            session_id=session_id,
            index_path=ready_snapshot["index_path"],
            chunks_path=ready_snapshot["chunks_path"],
            status="ready",
        )
        metadata_published = True
        document_repo.update_document_status(
            document_id,
            "ready",
            chunk_count=chunk_count,
        )
    except Exception as exc:
        logger.exception(
            "Failed to publish ready index snapshot session_id=%s snapshot_id=%s; rolling back",
            session_id,
            snapshot_id,
        )
        rollback_ok = snapshot_repo.rollback_snapshot_promotion(
            snapshot_id=snapshot_id,
            previous_ready_snapshot_id=(
                previous_ready_snapshot["id"] if previous_ready_snapshot is not None else None
            ),
            error_message=str(exc),
        )
        if metadata_published:
            try:
                _restore_index_publication(previous_index_metadata, ready_snapshot)
            except Exception as restore_exc:
                restore_error = RuntimeError("索引元数据恢复失败")
                setattr(restore_error, "candidate_snapshot", ready_snapshot)
                setattr(restore_error, "preserve_candidate_snapshot_files", True)
                raise restore_error from restore_exc
        if not rollback_ok:
            raise RuntimeError("索引快照回滚失败") from exc
        raise
    discard_store(session_id)
    logger.info(
        "Committed ready index snapshot session_id=%s snapshot_id=%s index_path=%s chunks_path=%s elapsed=%.2fs",
        session_id,
        snapshot_id,
        ready_snapshot["index_path"],
        ready_snapshot["chunks_path"],
        time.monotonic() - start,
    )
    return ready_snapshot


def cleanup_snapshot_files(snapshot: dict | None) -> None:
    if snapshot is None:
        return
    _unlink_if_exists(Path(snapshot["index_path"]))
    _unlink_if_exists(Path(snapshot["chunks_path"]))


def _snapshot_index_path(session_id: str, candidate_token: str) -> Path:
    snapshot_dir = session_indexes_dir(session_id) / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    return snapshot_dir / f"{candidate_token}.faiss.index"


def _snapshot_chunks_path(session_id: str, candidate_token: str) -> Path:
    snapshot_dir = session_indexes_dir(session_id) / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    return snapshot_dir / f"{candidate_token}.chunks.json"


def _unlink_if_exists(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


def _restore_index_publication(previous_index_metadata: dict | None, ready_snapshot: dict) -> None:
    if previous_index_metadata is not None:
        index_repo.upsert_index(
            session_id=previous_index_metadata["session_id"],
            index_path=previous_index_metadata["index_path"],
            chunks_path=previous_index_metadata["chunks_path"],
            status=previous_index_metadata["status"],
        )
        return
    index_repo.upsert_index(
        session_id=ready_snapshot["session_id"],
        index_path=ready_snapshot["index_path"],
        chunks_path=ready_snapshot["chunks_path"],
        status="failed",
    )
