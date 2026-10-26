import json
import logging
import shutil
import uuid
from contextlib import suppress
from pathlib import Path

from backend.application import index_maintenance
from backend.config import data_dir, settings
from backend.core.model.records import DocumentRecord
from backend.domain.exceptions import (
    ChunkNotFoundError,
    JobInProgressError,
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
    block_ids = metadata.block_ids or []
    document = document_repo.get_document(document_id)
    return {
        "document_id": document_id,
        "chunk_index": metadata.chunk_index,
        "section": metadata.section,
        "section_path": metadata.section_path or [],
        "page_start": metadata.page_start,
        "page_end": metadata.page_end,
        "type": metadata.type,
        "text": chunk.text,
        "block_ids": block_ids,
        "blocks": _resolve_block_boxes(
            document.get("parsed_ir_path") if document else None,
            block_ids,
        ),
    }


def get_document_file(session_id: str, document_id: str) -> Path:
    """Return the stored PDF path, refusing anything outside the data directory."""
    document = _get_owned_document(session_id, document_id)
    path = Path(document["file_path"]).resolve()
    root = data_dir().resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise DocumentNotFoundError(
            f"Document file not found: {document_id}",
            session_id=session_id,
            document_id=document_id,
        )
    return path


def _get_owned_document(session_id: str, document_id: str) -> dict:
    document = document_repo.get_document(document_id)
    if document is None or document["session_id"] != session_id:
        raise DocumentNotFoundError(
            f"Document not found: {document_id}",
            session_id=session_id,
            document_id=document_id,
        )
    return document


def _resolve_block_boxes(ir_path: str | None, block_ids: list[str]) -> list[dict]:
    """Map cited block ids to page numbers and normalized (0-1) boxes.

    The IR stores bbox in PDF points; normalizing here keeps the frontend free
    of page-size math and works for any render scale.
    """
    if not ir_path or not block_ids:
        return []
    payload = _load_ir_payload(ir_path)
    if payload is None:
        return []

    wanted = set(block_ids)
    pages = {page.get("page_number"): page for page in payload.get("pages") or []}
    boxes: list[dict] = []
    for block in _iter_ir_blocks(payload):
        if block.get("id") not in wanted:
            continue
        page_number = block.get("page_number") or 0
        boxes.append(
            {
                "id": block["id"],
                "page_number": page_number,
                "bbox": _normalize_bbox(block.get("bbox"), pages.get(page_number)),
            }
        )
    return boxes


def _normalize_bbox(bbox: object, page: dict | None) -> dict[str, float] | None:
    if not isinstance(bbox, dict) or page is None:
        return None
    width = float(page.get("width") or 0)
    height = float(page.get("height") or 0)
    if width <= 0 or height <= 0:
        return None
    try:
        x0 = float(bbox.get("x0", 0.0)) / width
        y0 = float(bbox.get("y0", 0.0)) / height
        x1 = float(bbox.get("x1", 0.0)) / width
        y1 = float(bbox.get("y1", 0.0)) / height
    except (TypeError, ValueError):
        return None
    return {
        "x0": max(0.0, min(1.0, x0)),
        "y0": max(0.0, min(1.0, y0)),
        "x1": max(0.0, min(1.0, x1)),
        "y1": max(0.0, min(1.0, y1)),
    }


def _load_ir_payload(ir_path: str) -> dict | None:
    path = Path(ir_path)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Unreadable parsed IR at %s", path)
        return None
    return payload if isinstance(payload, dict) else None


def delete_document(session_id: str, document_id: str) -> None:
    """硬删除文档：数据库行 → 分块 → 磁盘产物 → 重建会话索引。

    索引重建失败时把当前快照置为 failed，宁可让用户重新索引，也不能让检索
    继续命中已删除的向量。
    """
    document = document_repo.get_document(document_id)
    if document is None or document["session_id"] != session_id:
        raise DocumentNotFoundError(
            f"Document not found: {document_id}",
            session_id=session_id,
            document_id=document_id,
        )

    _reject_if_job_running(session_id)

    chunk_repo.delete_chunks_for_document(document_id)
    document_repo.delete_document(document_id)
    _remove_document_files(document)

    try:
        index_maintenance.refresh_after_document_change(session_id)
    except Exception:
        logger.exception("Index rebuild failed after deleting document=%s", document_id)
        index_maintenance.invalidate_session_index(session_id, "索引重建失败")


def _reject_if_job_running(session_id: str) -> None:
    """删除 / 归档必须等摄取结束，否则 worker 会边写 chunk 边被删（FK 冲突）。"""
    if job_repo.has_running_job(session_id):
        raise JobInProgressError(
            "Session is still being processed, try again later.", session_id=session_id
        )


def _remove_document_files(document: DocumentRecord) -> None:
    for raw in (
        document.get("file_path"),
        document.get("parsed_markdown_path"),
        document.get("quality_report_path"),
    ):
        if raw:
            with suppress(OSError):
                Path(raw).unlink()

    ir_path = document.get("parsed_ir_path")
    if not ir_path:
        return
    artifact_dir = Path(ir_path).parent
    root = data_dir().resolve()
    if artifact_dir.resolve().is_relative_to(root):
        with suppress(OSError):
            shutil.rmtree(artifact_dir)


def list_library_documents(user_id: str | None) -> list[dict]:
    """文献库列表：跨会话、跨文档的统一视图。"""
    return [
        {
            "document_id": row["id"],
            "session_id": row["session_id"],
            "session_title": row["session_title"],
            "filename": row["filename"],
            "status": row["status"],
            "chunk_count": row["chunk_count"],
            "file_size": row["file_size"],
            "parse_quality_status": row["parse_quality_status"],
            "updated_at": row["updated_at"],
        }
        for row in document_repo.list_documents_with_session(user_id)
    ]


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


def _iter_ir_blocks(payload: dict) -> list[dict]:
    """IR 可能把 blocks 放在文档级，也可能只放在页级。"""
    blocks = payload.get("blocks") or []
    if blocks:
        return blocks
    return [block for page in payload.get("pages") or [] for block in page.get("blocks") or []]


def _load_ir_blocks(ir_path: str | None) -> list[dict]:
    """Flatten ``document.ir.json`` into ordered, renderable blocks."""
    if not ir_path:
        return []
    payload = _load_ir_payload(ir_path)
    if payload is None:
        return []

    raw_blocks = _iter_ir_blocks(payload)
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
