from typing import Literal

from pydantic import BaseModel, Field


BlockType = Literal[
    "title",
    "heading",
    "paragraph",
    "table",
    "figure_caption",
    "table_caption",
    "formula",
    "footnote",
    "reference",
    "header_footer",
    "unknown",
]
QualityStatus = Literal["good", "usable_with_warnings", "poor", "failed"]


class BBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float


class BlockLink(BaseModel):
    target_block_id: str
    relation: str


class BlockIR(BaseModel):
    id: str
    page_number: int
    block_index: int
    type: BlockType
    text: str
    bbox: BBox
    reading_order: int
    section_path: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    links: list[BlockLink] = Field(default_factory=list)


class PageIR(BaseModel):
    page_number: int
    width: float
    height: float
    rotation: int
    blocks: list[BlockIR] = Field(default_factory=list)


class QualityReport(BaseModel):
    parser_name: str
    parser_version: str
    page_count: int
    text_block_count: int = 0
    heading_count: int = 0
    table_count: int = 0
    figure_caption_count: int = 0
    table_caption_count: int = 0
    formula_block_count: int = 0
    filtered_header_footer_count: int = 0
    low_confidence_block_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    overall_status: QualityStatus = "good"


class DocumentIR(BaseModel):
    document_id: str
    filename: str
    page_count: int
    parser_name: str
    parser_version: str
    pages: list[PageIR]
    blocks: list[BlockIR] = Field(default_factory=list)
    outline: list[str] = Field(default_factory=list)
    quality_report: QualityReport
