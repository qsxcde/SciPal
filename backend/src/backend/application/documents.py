import json
import logging
import uuid
from contextlib import suppress
from pathlib import Path

from backend.config import settings
from backend.domain.exceptions import (
    ChunkNotFoundError,
    DocumentNotFoundError,
    InvalidUploadError,
    SessionNotFoundError,
    UploadTooLargeError,
)
from backend.domain.states import DocumentStage
from backend.storage.sqlite import chunks as chunk_repo
from backend.storage.sqlite import documents as document_repo
from backend.storage.sqlite import jobs as job_repo
from backend.storage.sqlite import sessions as session_repo
from backend.storage.paths import session_document_file_path

logger = logging.getLogger(__name__)


def _validate_upload(file_size: int | None, pdf_bytes: bytes) -> None:
    if file_size is None:
        raise InvalidUploadError("Cannot determine file size")
    if file_size > settings.upload_max_bytes:
        raise UploadTooLargeError(f"File too large (max {settings.upload_max_bytes} bytes)")
    if not pdf_bytes.startswith(b"%PDF"):
        raise InvalidUploadError("Uploaded file is not a valid PDF")


def intake_document_upload(
    session_id: str,
    filename: str,
    mime_type: str,
    pdf_bytes: bytes,
    file_size: int | None = None,
) -> dict:
    """Persist upload intake state and enqueue an ingestion job."""
    _validate_upload(file_size or len(pdf_bytes), pdf_bytes)
    session = session_repo.get_session(session_id)
    if session is None:
        raise SessionNotFoundError(
            f"Session not found: {session_id}", session_id=session_id
        )
    document_id = str(uuid.uuid4())
    file_path = session_document_file_path(session_id, document_id)
    document = None
    job = None
    try:
        file_path.write_bytes(pdf_bytes)
        document = document_repo.create_document(
            session_id=session_id,
            filename=filename,
            file_path=str(file_path),
            mime_type=mime_type,
            file_size=len(pdf_bytes),
            document_id=document_id,
        )
        job = job_repo.create_job(
            session_id=session_id,
            document_id=document_id,
            job_type="document_ingestion",
            stage=DocumentStage.uploaded,
            payload_json=json.dumps(
                {
                    "document_id": document_id,
                    "filename": filename,
                    "file_path": str(file_path),
                },
                ensure_ascii=False,
            ),
        )
    except Exception:
        with suppress(RuntimeError, OSError):
            document_repo.delete_document(document_id)
        with suppress(FileNotFoundError):
            file_path.unlink()
        raise

    session_repo.touch_session(session_id)
    with suppress(RuntimeError, OSError):
        if session["title"] == settings.msg_default_session_title:
            session_repo.update_session_title(session_id, document["filename"])
    return {
        "document": document,
        "job": job,
    }


def get_source_chunk(session_id: str, document_id: str, chunk_index: int) -> dict:
    """Resolve a citation back to its full chunk text for the reader panel."""
    chunk = chunk_repo.get_chunk(session_id, document_id, chunk_index)
    if chunk is None:
        raise ChunkNotFoundError(
            f"Source chunk not found: document={document_id} chunk={chunk_index}",
            session_id=session_id,
            document_id=document_id,
            chunk_index=chunk_index,
        )
    metadata = chunk.metadata
    return {
        "document_id": document_id,
        "chunk_index": metadata.chunk_index,
        "section": metadata.section,
        "section_path": metadata.section_path or [],
        "page_start": metadata.page_start,
        "page_end": metadata.page_end,
        "type": metadata.type,
        "text": chunk.text,
        "block_ids": metadata.block_ids or [],
    }


def get_document_content(session_id: str, document_id: str) -> dict:
    """Return the parsed body blocks of a document for the reader panel.

    Blocks keep their original ``id`` so a citation can scroll to the exact
    paragraph that produced it.
    """
    document = document_repo.get_document(document_id)
    if document is None or document["session_id"] != session_id:
        raise DocumentNotFoundError(
            f"Document not found: {document_id}",
            session_id=session_id,
            document_id=document_id,
        )

    return {
        "document_id": document["id"],
        "filename": document["filename"],
        "status": document["status"],
        "parser_name": document["parser_name"],
        "parse_quality_status": document["parse_quality_status"],
        "chunk_count": document["chunk_count"],
        "blocks": _load_ir_blocks(document["parsed_ir_path"]),
    }


def _load_ir_blocks(ir_path: str | None) -> list[dict]:
    """Flatten ``document.ir.json`` into ordered, renderable blocks."""
    if not ir_path:
        return []
    path = Path(ir_path)
    if not path.is_file():
        return []

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Unreadable parsed IR at %s", path)
        return []

    raw_blocks = payload.get("blocks") or [
        block for page in payload.get("pages") or [] for block in page.get("blocks") or []
    ]
    ordered = sorted(
        raw_blocks,
        key=lambda block: (
            block.get("page_number") or 0,
            block.get("reading_order") or 0,
            block.get("block_index") or 0,
        ),
    )

    blocks: list[dict] = []
    for block in ordered:
        text = (block.get("text") or "").strip()
        if not text or block.get("type") == "header_footer":
            continue
        blocks.append(
            {
                "id": block.get("id") or "",
                "type": block.get("type") or "unknown",
                "text": text,
                "section_path": block.get("section_path") or [],
                "page_number": block.get("page_number") or 0,
            }
        )
    return blocks


def recover_orphaned_documents() -> None:
    """Scan for documents stuck in 'uploaded' status without a corresponding job and clean them up."""
    orphaned = document_repo.list_orphaned_uploaded_documents()
    for doc in orphaned:
        logger.warning(
            "Cleaning up orphaned document document_id=%s session_id=%s filename=%s",
            doc["id"], doc["session_id"], doc["filename"],
        )
        with suppress(RuntimeError, OSError):
            document_repo.delete_document(doc["id"])
        with suppress(FileNotFoundError):
            Path(doc["file_path"]).unlink()
