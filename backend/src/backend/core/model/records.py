"""Typed shapes returned by the SQLite repositories.

These are dicts at runtime (zero-cost), but they give mypy a contract so call
sites using the wrong key (e.g. document["state"]) fail at check time.
"""

from typing import TypedDict


class DocumentRecord(TypedDict):
    id: str
    session_id: str
    filename: str
    file_path: str
    mime_type: str
    file_size: int
    chunk_count: int
    status: str
    error_message: str | None
    created_at: str
    updated_at: str


class MessageRecord(TypedDict):
    id: str
    session_id: str
    role: str
    content: str
    sources: list[dict]
    status: str
    client_message_id: str | None
    model: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    created_at: str
class JobRecord(TypedDict):
    id: str
    session_id: str
    document_id: str | None
    type: str
    status: str
    stage: str
    attempt: int
    error_message: str | None
    payload_json: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None
class SessionRecord(TypedDict):
    id: str
    title: str
    user_id: str | None
    created_at: str
    updated_at: str
    last_opened_at: str
    is_archived: int
    is_pinned: int


class IndexRecord(TypedDict):
    id: str
    session_id: str
    index_path: str
    chunks_path: str
    status: str
    created_at: str
    updated_at: str
class SessionSummaryRecord(SessionRecord):
    document_count: int
    message_count: int
    indexed_chunks: int


class SnapshotRecord(TypedDict):
    id: str
    session_id: str
    status: str
    index_path: str
    chunks_path: str
    document_ids: list[str]
    error_message: str | None
    created_at: str
    updated_at: str
