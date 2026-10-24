"""Document transfer models: session snapshot entries and upload intake."""

from typing import Literal

from pydantic import BaseModel


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


class DocumentIntakeResponse(BaseModel):
    document_id: str
    job_id: str
    document_status: Literal["uploaded"]
    job_status: Literal["queued", "running"]
    session_status: Literal["processing"]
