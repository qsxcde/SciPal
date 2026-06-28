from typing import Literal

from pydantic import BaseModel
from fastapi import APIRouter, Depends, UploadFile, File
from backend.app.core.auth import get_current_user
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
    user: dict = Depends(get_current_user),
) -> DocumentIntakeResponse:
    pdf_bytes = file.file.read()
    intake = intake_document_upload(
        session_id=session_id,
        filename=file.filename or "paper.pdf",
        mime_type=file.content_type or "application/pdf",
        pdf_bytes=pdf_bytes,
        file_size=file.size,
    )
    return DocumentIntakeResponse(
        document_id=intake["document"]["id"],
        job_id=intake["job"]["id"],
        document_status=intake["document"]["status"],
        job_status=intake["job"]["status"],
        session_status="processing",
    )
