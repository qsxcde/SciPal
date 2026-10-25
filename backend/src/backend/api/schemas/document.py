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


class LibraryDocumentSummary(BaseModel):
    """文献库列表项：文档 + 所属会话标题。"""

    document_id: str
    session_id: str
    session_title: str
    filename: str
    status: str
    chunk_count: int
    file_size: int
    parse_quality_status: str | None = None
    updated_at: str


class DocumentIntakeResponse(BaseModel):
    document_id: str
    job_id: str
    document_status: Literal["uploaded"]
    job_status: Literal["queued", "running"]
    session_status: Literal["processing"]


class PaperBlock(BaseModel):
    """Reader 用的正文块，`id` 与 citations 的 block_ids 对齐。"""

    id: str
    type: str
    text: str
    section_path: list[str]
    page_number: int


class DocumentContentResponse(BaseModel):
    document_id: str
    filename: str
    status: str
    parser_name: str | None = None
    parse_quality_status: str | None = None
    chunk_count: int
    blocks: list[PaperBlock]


class SourceChunkResponse(BaseModel):
    """回复引用的原文定位结果，供阅读器面板展示。"""

    document_id: str
    chunk_index: int
    section: str
    section_path: list[str]
    page_start: int | None = None
    page_end: int | None = None
    type: str
    text: str
    block_ids: list[str]
