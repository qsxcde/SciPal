"""HTTP transfer models (request/response and SSE payloads)."""

from backend.api.schemas.auth import AuthRequest, AuthResponse, UserResponse
from backend.api.schemas.chat import (
    ChatMessage,
    ChatStreamDoneEvent,
    ChatStreamErrorEvent,
    ChatStreamEvent,
    ChatStreamSourcesEvent,
    ChatStreamStatusEvent,
    ChatStreamTokenEvent,
    ChatStreamWarningEvent,
)
from backend.api.schemas.document import (
    DocumentContentResponse,
    DocumentIntakeResponse,
    DocumentSummary,
    LibraryDocumentSummary,
    PaperBlock,
    SourceChunkResponse,
)
from backend.api.schemas.session import (
    IndexSnapshotSummary,
    JobSummary,
    PersistedMessage,
    RetrievalIndexSummary,
    SessionCreateResponse,
    SessionSnapshot,
    SessionSummary,
    SessionUpdateRequest,
)

__all__ = [
    "AuthRequest",
    "AuthResponse",
    "ChatMessage",
    "ChatStreamDoneEvent",
    "ChatStreamErrorEvent",
    "ChatStreamEvent",
    "ChatStreamSourcesEvent",
    "ChatStreamStatusEvent",
    "ChatStreamTokenEvent",
    "ChatStreamWarningEvent",
    "DocumentContentResponse",
    "DocumentIntakeResponse",
    "DocumentSummary",
    "LibraryDocumentSummary",
    "IndexSnapshotSummary",
    "JobSummary",
    "PaperBlock",
    "PersistedMessage",
    "RetrievalIndexSummary",
    "SessionCreateResponse",
    "SessionSnapshot",
    "SessionSummary",
    "SessionUpdateRequest",
    "SourceChunkResponse",
    "UserResponse",
]
