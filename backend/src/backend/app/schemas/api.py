from pydantic import BaseModel, Field
from typing import Literal

from backend.rag.ingestion.metadata import SourceRef
from backend.domain.states import DocumentStage
from backend.domain.states import IndexSnapshotStatus
from backend.domain.states import JobStatus
from backend.domain.states import SessionStatus


class SessionCreateResponse(BaseModel):
    session_id: str


class DocumentSummary(BaseModel):
    id: str
    session_id: str
    filename: str
    file_path: str
    mime_type: str
    file_size: int
    chunk_count: int
    status: str
    error_message: str | None = None
    parsed_ir_path: str | None = None
    parsed_markdown_path: str | None = None
    quality_report_path: str | None = None
    parser_name: str | None = None
    parser_version: str | None = None
    parse_quality_status: str | None = None
    created_at: str
    updated_at: str


class PersistedMessage(BaseModel):
    id: str
    session_id: str
    role: Literal["user", "assistant"]
    content: str
    sources: list[SourceRef] = Field(default_factory=list)
    status: Literal["complete", "failed"]
    created_at: str


class RetrievalIndexSummary(BaseModel):
    id: str
    session_id: str
    index_path: str
    chunks_path: str
    status: IndexSnapshotStatus
    updated_at: str


class JobSummary(BaseModel):
    id: str
    session_id: str
    document_id: str | None = None
    type: str
    status: JobStatus
    stage: DocumentStage
    attempt: int
    error_message: str | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None


class IndexSnapshotSummary(BaseModel):
    id: str
    session_id: str
    status: IndexSnapshotStatus
    index_path: str
    chunks_path: str
    document_ids: list[str]
    updated_at: str
    error_message: str | None = None


class SessionSummary(BaseModel):
    id: str
    title: str
    user_id: str | None = None
    created_at: str
    updated_at: str
    last_opened_at: str
    is_archived: bool = False
    is_pinned: bool = False
    document_count: int = 0
    message_count: int = 0
    indexed_chunks: int = 0


class SessionSnapshot(BaseModel):
    id: str
    title: str
    user_id: str | None = None
    created_at: str
    updated_at: str
    last_opened_at: str
    is_archived: bool = False
    is_pinned: bool = False
    documents: list[DocumentSummary]
    messages: list[PersistedMessage]
    status: SessionStatus
    jobs: list[JobSummary]
    indexed_chunks: int
    active_index: IndexSnapshotSummary | None = None
    retrieval_index: RetrievalIndexSummary | None = None


class SessionUpdateRequest(BaseModel):
    title: str | None = None
    is_pinned: bool | None = None


class DocumentUploadResponse(BaseModel):
    doc_id: str
    chunk_count: int


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"] = "user"
    content: str


class ChatStreamTokenEvent(BaseModel):
    type: Literal["token"]
    value: str


class ChatStreamStatusEvent(BaseModel):
    type: Literal["status"]
    value: Literal["waiting_for_index", "retrieving", "generating"]


class ChatStreamSourcesEvent(BaseModel):
    type: Literal["sources"]
    value: list[SourceRef]


class ChatStreamErrorEvent(BaseModel):
    type: Literal["error"]
    value: str


class ChatStreamWarningEvent(BaseModel):
    type: Literal["warning"]
    value: str


class ChatStreamDoneEvent(BaseModel):
    type: Literal["done"]


ChatStreamEvent = ChatStreamStatusEvent | ChatStreamTokenEvent | ChatStreamSourcesEvent | ChatStreamErrorEvent | ChatStreamWarningEvent | ChatStreamDoneEvent
