from fastapi import APIRouter, Depends, File, UploadFile

from backend.api.deps import get_accessible_session
from backend.api.schemas import (
    DocumentContentResponse,
    DocumentIntakeResponse,
    LibraryDocumentSummary,
    SourceChunkResponse,
)
from backend.api.security import get_current_user
from backend.application.documents import (
    delete_document as delete_document_use_case,
    get_document_content,
    get_source_chunk,
    intake_document_upload,
    list_library_documents,
)

router = APIRouter()


@router.get("/documents", response_model=list[LibraryDocumentSummary])
def list_documents(user: dict = Depends(get_current_user)) -> list[LibraryDocumentSummary]:
    """跨会话的文献库列表（已归档会话不计入）。"""
    return [
        LibraryDocumentSummary(**item)
        for item in list_library_documents(user.get("id") or None)
    ]


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


@router.delete("/sessions/{session_id}/documents/{document_id}")
def delete_document(
    session_id: str,
    document_id: str,
    session: dict = Depends(get_accessible_session),
) -> dict:
    """删除单篇文档（行 + 分块 + 磁盘产物）并重建会话索引。"""
    delete_document_use_case(session["id"], document_id)
    return {"status": "deleted"}


@router.get(
    "/sessions/{session_id}/documents/{document_id}/content",
    response_model=DocumentContentResponse,
)
def read_document_content(
    session_id: str,
    document_id: str,
    session: dict = Depends(get_accessible_session),
) -> DocumentContentResponse:
    """返回解析后的结构化正文，供阅读器渲染与引用定位。"""
    return DocumentContentResponse(
        **get_document_content(session_id=session["id"], document_id=document_id)
    )


@router.get(
    "/sessions/{session_id}/documents/{document_id}/chunks/{chunk_index}",
    response_model=SourceChunkResponse,
)
def read_source_chunk(
    session_id: str,
    document_id: str,
    chunk_index: int,
    session: dict = Depends(get_accessible_session),
) -> SourceChunkResponse:
    """把回答里的引用还原为原文段落，供前端阅读器定位。"""
    return SourceChunkResponse(
        **get_source_chunk(
            session_id=session["id"],
            document_id=document_id,
            chunk_index=chunk_index,
        )
    )
