import logging
import shutil
import time
from pathlib import Path

from backend.app.services.index_service import build_candidate_snapshot
from backend.app.services.index_service import cleanup_snapshot_files
from backend.app.services.index_service import commit_ready_snapshot
from backend.domain.exceptions import PaperParseError
from backend.domain.exceptions import SnapshotCommitError
from backend.domain.states import DocumentStage
from backend.rag.ingestion.artifacts import save_ingestion_artifacts
from backend.rag.ingestion.metadata import Chunk
from backend.rag.ingestion.pipeline import process_pdf_document
from backend.storage.paths import raw_session_dir
from backend.storage.sqlite import chunks as chunk_repo
from backend.storage.sqlite import documents as document_repo
from backend.storage.sqlite import index_snapshots as snapshot_repo
from backend.storage.vector_db.registry import discard_store

logger = logging.getLogger(__name__)


def run_document_ingestion_job(
    session_id: str,
    document: dict,
    pdf_bytes: bytes,
) -> dict:
    document_id = document["id"]
    snapshot = None
    try:
        chunks = _do_parse_document(session_id, document, pdf_bytes)
        snapshot = _do_build_and_commit_index(session_id, document_id, chunks)
        return {
            "snapshot": snapshot,
            "chunk_count": len(chunks),
        }
    except SnapshotCommitError as exc:
        logger.exception(
            "Document ingestion failed session_id=%s document_id=%s",
            session_id,
            document_id,
        )
        _mark_failed(
            document_id,
            session_id,
            exc.candidate_snapshot,
            exc,
            preserve_candidate_snapshot_files=exc.preserve_candidate_snapshot_files,
        )
        raise
    except Exception as exc:
        logger.exception(
            "Document ingestion failed session_id=%s document_id=%s",
            session_id,
            document_id,
        )
        _mark_failed(document_id, session_id, snapshot, exc)
        raise


def _do_parse_document(session_id: str, document: dict, pdf_bytes: bytes) -> list[Chunk]:
    document_id = document["id"]
    logger.info(
        "Starting document parsing session_id=%s document_id=%s filename=%s bytes=%d",
        session_id, document_id, document["filename"], len(pdf_bytes),
    )

    document_repo.update_document_status(document_id, DocumentStage.parsing)
    parse_start = time.monotonic()
    ingestion_result = process_pdf_document(
        pdf_bytes=pdf_bytes,
        paper_id=document_id,
        filename=document["filename"],
    )
    logger.info(
        "Completed document parsing session_id=%s document_id=%s parser=%s version=%s "
        "pages=%d chunks=%d quality=%s elapsed=%.2fs",
        session_id, document_id,
        ingestion_result.document_ir.parser_name,
        ingestion_result.document_ir.parser_version,
        ingestion_result.document_ir.page_count,
        len(ingestion_result.chunks),
        ingestion_result.quality_report.overall_status,
        time.monotonic() - parse_start,
    )

    artifacts = save_ingestion_artifacts(
        artifact_dir=raw_session_dir(session_id) / "parsed" / document_id,
        document_ir=ingestion_result.document_ir,
        raw_markdown=ingestion_result.raw_markdown,
        normalized_markdown=ingestion_result.markdown,
        quality_report=ingestion_result.quality_report,
    )
    logger.info(
        "Saved ingestion artifacts session_id=%s document_id=%s ir_path=%s",
        session_id, document_id, artifacts.ir_path,
    )

    document_repo.update_document_artifacts(
        document_id=document_id,
        parsed_ir_path=str(artifacts.ir_path),
        parsed_markdown_path=str(artifacts.markdown_path),
        quality_report_path=str(artifacts.quality_report_path),
        parser_name=ingestion_result.document_ir.parser_name,
        parser_version=ingestion_result.document_ir.parser_version,
        parse_quality_status=ingestion_result.quality_report.overall_status,
    )
    chunks = ingestion_result.chunks
    document_repo.update_document_status(document_id, DocumentStage.parsed)

    chunk_repo.delete_chunks_for_document(document_id)
    chunk_repo.insert_chunks(
        session_id=session_id,
        document_id=document_id,
        parsed_chunks=chunks,
    )
    document_repo.update_document_status(
        document_id,
        DocumentStage.chunked,
        chunk_count=len(chunks),
    )

    logger.info(
        "Inserted %d chunks session_id=%s document_id=%s",
        len(chunks), session_id, document_id,
    )
    return chunks


def _do_build_and_commit_index(session_id: str, document_id: str, chunks: list[Chunk]) -> dict:
    logger.info(
        "Building candidate index snapshot session_id=%s document_id=%s chunk_count=%d",
        session_id, document_id, len(chunks),
    )

    document_repo.update_document_status(
        document_id, DocumentStage.indexing, chunk_count=len(chunks),
    )

    snapshot = build_candidate_snapshot(session_id, document_id)
    logger.info(
        "Built candidate index snapshot session_id=%s document_id=%s snapshot_id=%s",
        session_id, document_id, snapshot["id"],
    )

    job_start = time.monotonic()
    ready_snapshot = commit_ready_snapshot(
        session_id, snapshot["id"], document_id, len(chunks),
    )
    logger.info(
        "Committed ready index snapshot session_id=%s document_id=%s snapshot_id=%s elapsed=%.2fs",
        session_id, document_id, ready_snapshot["id"],
        time.monotonic() - job_start,
    )
    return ready_snapshot


def _mark_failed(
    document_id: str,
    session_id: str,
    snapshot: dict | None,
    exc: Exception,
    preserve_candidate_snapshot_files: bool = False,
) -> None:
    if snapshot is not None:
        snapshot_repo.mark_snapshot_failed(snapshot["id"], str(exc))
        if not preserve_candidate_snapshot_files:
            cleanup_snapshot_files(snapshot)
    chunk_repo.delete_chunks_for_document(document_id)
    _clear_document_artifacts(document_id)
    document_repo.update_document_status(
        document_id,
        DocumentStage.failed,
        chunk_count=0,
        error_message=str(exc),
    )
    discard_store(session_id)
    _cleanup_parsed_artifacts(session_id, document_id)


def _cleanup_parsed_artifacts(session_id: str, document_id: str) -> None:
    artifact_dir = raw_session_dir(session_id) / "parsed" / document_id
    if not _is_safe_parsed_artifact_dir(artifact_dir, session_id):
        return
    shutil.rmtree(artifact_dir, ignore_errors=True)


def _is_safe_parsed_artifact_dir(path: Path, session_id: str) -> bool:
    parsed_root = (raw_session_dir(session_id) / "parsed").resolve()
    target = path.resolve()
    return target == parsed_root / target.name and target.parent == parsed_root


def _clear_document_artifacts(document_id: str) -> None:
    document_repo.update_document_artifacts(
        document_id=document_id,
        parsed_ir_path=None,
        parsed_markdown_path=None,
        quality_report_path=None,
        parser_name=None,
        parser_version=None,
        parse_quality_status=None,
    )
