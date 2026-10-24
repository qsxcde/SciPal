from fastapi import APIRouter, Depends, File, UploadFile

from backend.api.deps import get_accessible_session
from backend.api.schemas import DocumentIntakeResponse
from backend.application.documents import intake_document_upload

router = APIRouter()


@router.post(
    "/sessions/{session_id}/documents",
    status_code=202,
    response_model=DocumentIntakeResponse,
)
def upload_document(
    session_id: str,
    file: UploadFile = File(...),
    session: dict = Depends(get_accessible_session),
) -> DocumentIntakeResponse:
    pdf_bytes = file.file.read()
    intake = intake_document_upload(
        session_id=session["id"],
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
