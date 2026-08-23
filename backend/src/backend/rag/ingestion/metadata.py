from pydantic import BaseModel
from typing import Literal


class ChunkMetadata(BaseModel):
    paper_id: str
    section: str
    chunk_index: int
    type: Literal["abstract", "paragraph", "table", "heading", "formula", "code", "caption", "reference"]
    section_path: list[str] | None = None
    page_start: int | None = None
    page_end: int | None = None
    bbox: dict[str, float] | None = None
    block_ids: list[str] | None = None
    block_types: list[str] | None = None
    linked_block_ids: list[str] | None = None
    confidence: float | None = None
    word_count: int | None = None
    char_count: int | None = None
    is_reference: bool = False


class Chunk(BaseModel):
    text: str
    metadata: ChunkMetadata


class SourceRef(BaseModel):
    paper_id: str | None = None
    section: str
    chunk_index: int
    text_excerpt: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    block_ids: list[str] | None = None
    confidence: float | None = None
