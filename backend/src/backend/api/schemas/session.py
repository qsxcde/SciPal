"""Session transfer models, including the aggregated session snapshot."""

from typing import Literal

from pydantic import BaseModel, Field

from backend.api.schemas.document import DocumentSummary
from backend.domain.models import SourceRef
from backend.domain.states import DocumentStage
from backend.domain.states import IndexSnapshotStatus
from backend.domain.states import JobStatus
from backend.domain.states import MessageStatus
from backend.domain.states import SessionStatus


class SessionCreateResponse(BaseModel):
    session_id: str


class PersistedMessage(BaseModel):
    id: str
    session_id: str
    role: Literal["user", "assistant"]
    content: str
    sources: list[SourceRef] = Field(default_factory=list)
    status: MessageStatus
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
