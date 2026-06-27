import json
import logging
import uuid
from contextlib import suppress
from pathlib import Path

from backend.domain.config import settings
from backend.domain.states import DocumentStage
from backend.storage.sqlite import documents as document_repo
from backend.storage.sqlite import jobs as job_repo
from backend.storage.sqlite import sessions as session_repo
from backend.storage.paths import session_document_file_path

logger = logging.getLogger(__name__)


def intake_document_upload(
    session_id: str,
    filename: str,
    mime_type: str,
    pdf_bytes: bytes,
) -> dict:
    """Persist upload intake state and enqueue an ingestion job."""
    document_id = str(uuid.uuid4())
    file_path = session_document_file_path(session_id, document_id)
    session = session_repo.get_session(session_id)
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
        session_repo.touch_session(session_id)
    except Exception:
        with suppress(RuntimeError, OSError):
            document_repo.delete_document(document_id)
        with suppress(FileNotFoundError):
            file_path.unlink()
        if session is not None:
            with suppress(RuntimeError, OSError):
                session_repo.restore_session_timestamps(
                    session_id=session_id,
                    updated_at=session["updated_at"],
                    last_opened_at=session["last_opened_at"],
                )
        raise

    with suppress(RuntimeError, OSError):
        if session and session["title"] == settings.msg_default_session_title:
            session_repo.update_session_title(session_id, document["filename"])
    return {
        "document": document,
        "job": job,
    }


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
