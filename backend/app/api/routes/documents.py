from typing import Literal

from pydantic import BaseModel
from fastapi import APIRouter, UploadFile, File, HTTPException
from backend.app.core.config import settings
from backend.storage.sqlite import sessions as session_repo
from backend.app.services.document_service import intake_document_upload

router = APIRouter()


class DocumentIntakeResponse(BaseModel):
    document_id: str
    job_id: str
    document_status: Literal["uploaded"]
    job_status: Literal["queued", "running"]
    session_status: Literal["processing"]


@router.post("/sessions/{session_id}/documents", status_code=202, response_model=DocumentIntakeResponse)
def upload_document(
    session_id: str,
    file: UploadFile = File(...),
):
    session = session_repo.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found. Please create a session first.")
    if file.size is None:
        raise HTTPException(status_code=413, detail="Cannot determine file size")
    if file.size > settings.upload_max_bytes:
        raise HTTPException(status_code=413, detail="File too large (max 50MB)")
    pdf_bytes = file.file.read()
    if not pdf_bytes.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid PDF")
    intake = intake_document_upload(
        session_id=session_id,
        filename=file.filename or "paper.pdf",
        mime_type=file.content_type or "application/pdf",
        pdf_bytes=pdf_bytes,
    )
    return {
        "document_id": intake["document"]["id"],
        "job_id": intake["job"]["id"],
        "document_status": intake["document"]["status"],
        "job_status": intake["job"]["status"],
        "session_status": "processing",
    }
