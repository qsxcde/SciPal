import re

from backend.rag.ingestion.document_ir import BBox, BlockType
from backend.rag.ingestion.reading_order import is_page_margin_block


HEADING_PATTERN = re.compile(r"^(abstract|references|conclusion|introduction|\d+(?:\.\d+)*\s+\S.*)$", re.IGNORECASE)
FIGURE_CAPTION_PATTERN = re.compile(r"^(fig\.|figure|图)\s*\d*", re.IGNORECASE)
TABLE_CAPTION_PATTERN = re.compile(r"^(table|表)\s*\d*", re.IGNORECASE)
REFERENCE_ENTRY_PATTERN = re.compile(r"^\[\d+\]")
NUMBERED_HEADING_PATTERN = re.compile(r"^(?P<number>\d+(?:\.\d+)*)\s+(?P<title>\S.*)$")


def detect_block_type(
    text: str,
    bbox: BBox,
    page_height: float,
    repeated_header_footer_texts: set[str],
    in_references: bool,
) -> BlockType:
    normalized = text.strip()
    if not normalized:
        return "unknown"
    if is_page_number(normalized, bbox, page_height):
        return "header_footer"
    if normalized in repeated_header_footer_texts and is_page_margin_block(bbox, page_height):
        return "header_footer"
    if HEADING_PATTERN.match(normalized) and len(normalized.split()) <= 12:
        return "heading"
    if in_references and REFERENCE_ENTRY_PATTERN.match(normalized):
        return "reference"
    if FIGURE_CAPTION_PATTERN.match(normalized):
        return "figure_caption"
    if TABLE_CAPTION_PATTERN.match(normalized):
        return "table_caption"
    if normalized.startswith("|") and normalized.count("|") >= 2:
        return "table"
    if looks_like_formula(normalized):
        return "formula"
    return "paragraph"


def clean_heading(text: str) -> str:
    normalized = text.strip().lstrip("#").strip()
    match = NUMBERED_HEADING_PATTERN.match(normalized)
    if match:
        return match.group("title").strip()
    return normalized


def confidence_for_type(block_type: BlockType, text: str) -> float:
    if block_type == "header_footer":
        return 0.99
    if block_type in {"heading", "reference", "figure_caption", "table_caption", "table"}:
        return 0.93
    if block_type == "formula":
        return 0.7 if text else 0.3
    if block_type == "unknown":
        return 0.4
    return 0.9


def is_page_number(text: str, bbox: BBox, page_height: float) -> bool:
    return text.isdigit() and is_page_margin_block(bbox, page_height)


def looks_like_formula(text: str) -> bool:
    if len(text.split()) > 12:
        return False
    math_tokens = ("=", "+", "-", "*", "/", "^", "≤", "≥", "∑", "∫")
    return sum(1 for token in math_tokens if token in text) >= 2
