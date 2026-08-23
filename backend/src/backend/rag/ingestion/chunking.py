from __future__ import annotations

from collections.abc import Iterable
import re

from backend.rag.ingestion.document_ir import BBox, BlockIR, DocumentIR
from backend.rag.ingestion.metadata import Chunk, ChunkMetadata


DEFAULT_CHUNK_SIZE = 2000
DEFAULT_CHUNK_OVERLAP = 120
SEPARATORS = ["\n\n", "\n", ". ", "。", "！", "？", " ", ""]
MERGEABLE_TYPES = {"paragraph", "figure_caption", "table_caption", "reference"}


def _estimate_tokens(text: str) -> int:
    """Rough token count: English ~1/4 char, CJK ~1/1.5 char."""
    cjk = sum(1 for c in text if "一" <= c <= "鿿" or 0x3400 <= ord(c) <= 0x4DBF)
    other = len(text) - cjk
    return max(1, int(cjk / 1.5 + other / 4))


def build_chunks(
    document_ir: DocumentIR,
    markdown: str,
    paper_id: str,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[Chunk]:
    if not _ordered_blocks(document_ir):
        return _build_markdown_only_chunks(markdown, paper_id, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    chunks: list[Chunk] = []
    text_buffer: list[BlockIR] = []

    def flush_text_buffer() -> None:
        nonlocal text_buffer
        if not text_buffer:
            return
        section_path = _section_path(text_buffer[0])
        body = "\n\n".join(_render_block(block) for block in text_buffer if block.text.strip()).strip()
        block_ids = [block.id for block in text_buffer]
        block_types = _unique(block.type for block in text_buffer)
        linked_block_ids = _linked_block_ids(text_buffer)
        confidence = min(block.confidence for block in text_buffer)
        bbox = _merge_bboxes([block.bbox for block in text_buffer]).model_dump()
        page_start = min(block.page_number for block in text_buffer)
        page_end = max(block.page_number for block in text_buffer)
        is_reference = _is_reference_section(section_path)
        chunk_type = "reference" if is_reference else _chunk_type(text_buffer[0])
        for part in _recursive_split(body, chunk_size=chunk_size, chunk_overlap=chunk_overlap):
            _append_chunk(
                chunks,
                paper_id=paper_id,
                section_path=section_path,
                body=part,
                chunk_type=chunk_type,
                block_ids=block_ids,
                block_types=block_types,
                linked_block_ids=linked_block_ids,
                confidence=confidence,
                bbox=bbox,
                page_start=page_start,
                page_end=page_end,
                is_reference=is_reference,
            )
        text_buffer = []

    for block in _ordered_blocks(document_ir):
        if block.type in {"title", "heading", "header_footer"}:
            continue
        if _is_code_block(block):
            flush_text_buffer()
            _append_single_block_chunk(chunks, paper_id, block, "code")
            continue
        if block.type == "reference":
            flush_text_buffer()
            _append_single_block_chunk(chunks, paper_id, block, "reference")
            continue
        if block.type in MERGEABLE_TYPES:
            if text_buffer and _section_path(text_buffer[0]) != _section_path(block):
                flush_text_buffer()
            text_buffer.append(block)
            continue
        flush_text_buffer()
        _append_single_block_chunk(chunks, paper_id, block, _chunk_type(block))
    flush_text_buffer()
    return chunks


def _build_markdown_only_chunks(
    markdown: str,
    paper_id: str,
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    section_path = ["Document"]
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        body = "\n\n".join(part.strip() for part in buffer if part.strip()).strip()
        buffer = []
        if not body:
            return
        is_reference = _is_reference_section(section_path)
        chunk_type = "reference" if is_reference else ("abstract" if section_path[-1].lower() == "abstract" else "paragraph")
        for part in _recursive_split(body, chunk_size=chunk_size, chunk_overlap=chunk_overlap):
            _append_chunk(
                chunks,
                paper_id=paper_id,
                section_path=section_path,
                body=part,
                chunk_type=chunk_type,
                block_ids=[],
                block_types=["markdown"],
                linked_block_ids=None,
                confidence=0.5,
                bbox=None,
                page_start=None,
                page_end=None,
                is_reference=is_reference,
            )

    for raw_line in markdown.strip().splitlines():
        line = raw_line.strip()
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            flush()
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip() or "Document"
            parent = section_path[: max(level - 1, 0)]
            section_path = [*parent, title] if parent else [title]
            continue
        if not line:
            flush()
            continue
        buffer.append(line)
    flush()
    if not chunks:
        _append_chunk(
            chunks,
            paper_id=paper_id,
            section_path=["Document"],
            body=markdown.strip(),
            chunk_type="paragraph",
            block_ids=[],
            block_types=["markdown"],
            linked_block_ids=None,
            confidence=0.5,
            bbox=None,
            page_start=None,
            page_end=None,
            is_reference=False,
        )
    return chunks


def _ordered_blocks(document_ir: DocumentIR) -> list[BlockIR]:
    blocks = document_ir.blocks or [block for page in document_ir.pages for block in page.blocks]
    return sorted(blocks, key=lambda block: (block.page_number, block.reading_order, block.block_index))


def _section_path(block: BlockIR) -> list[str]:
    return block.section_path or ["Document"]


def _heading_prefix(section_path: list[str]) -> str:
    return "\n".join(f"{'#' * min(index + 2, 6)} {title}" for index, title in enumerate(section_path))


def _render_block(block: BlockIR) -> str:
    text = block.text.strip()
    if block.type == "table":
        return f"[Table on page {block.page_number}]\n{text}" if text else f"[Table on page {block.page_number}]"
    if block.type == "formula":
        return text or f"[Formula on page {block.page_number} near {' > '.join(_section_path(block))}]"
    if block.type == "figure_caption":
        return f"**Figure:** {text}" if text else ""
    if block.type == "table_caption":
        return f"**Table:** {text}" if text else ""
    return text


def _chunk_type(block: BlockIR) -> str:
    if block.type == "table":
        return "table"
    if block.type == "formula":
        return "formula"
    if block.type in {"figure_caption", "table_caption"}:
        return "caption"
    if _is_reference_section(_section_path(block)) or block.type == "reference":
        return "reference"
    section = _section_path(block)[-1].lower()
    return "abstract" if section == "abstract" else "paragraph"


def _is_code_block(block: BlockIR) -> bool:
    return block.text.strip().startswith("```")


def _is_reference_section(section_path: list[str]) -> bool:
    return any(part.strip().lower() in {"references", "bibliography"} for part in section_path)


def _append_single_block_chunk(chunks: list[Chunk], paper_id: str, block: BlockIR, chunk_type: str) -> None:
    _append_chunk(
        chunks,
        paper_id=paper_id,
        section_path=_section_path(block),
        body=_render_block(block),
        chunk_type=chunk_type,
        block_ids=[block.id],
        block_types=[block.type],
        linked_block_ids=_linked_block_ids([block]),
        confidence=block.confidence,
        bbox=block.bbox.model_dump(),
        page_start=block.page_number,
        page_end=block.page_number,
        is_reference=_is_reference_section(_section_path(block)) or block.type == "reference",
    )


def _append_chunk(
    chunks: list[Chunk],
    *,
    paper_id: str,
    section_path: list[str],
    body: str,
    chunk_type: str,
    block_ids: list[str],
    block_types: list[str],
    linked_block_ids: list[str] | None,
    confidence: float,
    bbox: dict[str, float] | None,
    page_start: int | None,
    page_end: int | None,
    is_reference: bool,
) -> None:
    body = body.strip()
    if not body:
        return
    text = f"{_heading_prefix(section_path)}\n\n{body}".strip()
    chunks.append(
        Chunk(
            text=text,
            metadata=ChunkMetadata(
                paper_id=paper_id,
                section=" > ".join(section_path),
                section_path=section_path,
                chunk_index=len(chunks),
                type=chunk_type,
                page_start=page_start,
                page_end=page_end,
                bbox=bbox,
                block_ids=block_ids,
                block_types=block_types,
                linked_block_ids=linked_block_ids,
                confidence=confidence,
                char_count=len(text),
                word_count=len(text.split()),
                is_reference=is_reference,
            ),
        )
    )


def _recursive_split(text: str, *, chunk_size: int, chunk_overlap: int) -> list[str]:
    text = text.strip()
    if _estimate_tokens(text) <= chunk_size:
        return [text] if text else []
    pieces = _split_by_separator(text, chunk_size)
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current}{piece}" if not current else f"{current} {piece}"
        if _estimate_tokens(candidate) <= chunk_size or not current:
            current = candidate
            continue
        chunks.append(current.strip())
        overlap = current[-chunk_overlap:].strip() if chunk_overlap > 0 else ""
        current = f"{overlap} {piece}".strip() if overlap else piece
    if current.strip():
        chunks.append(current.strip())
    return chunks


def _split_by_separator(text: str, chunk_size: int) -> list[str]:
    if _estimate_tokens(text) <= chunk_size:
        return [text]
    for separator in SEPARATORS:
        if separator and separator in text:
            result: list[str] = []
            for part in text.split(separator):
                part = part.strip()
                if not part:
                    continue
                result.extend(_split_by_separator(part, chunk_size))
            return result
    return [text[index : index + chunk_size] for index in range(0, len(text), chunk_size)]


def _merge_bboxes(bboxes: list[BBox]) -> BBox:
    return BBox(
        x0=min(bbox.x0 for bbox in bboxes),
        y0=min(bbox.y0 for bbox in bboxes),
        x1=max(bbox.x1 for bbox in bboxes),
        y1=max(bbox.y1 for bbox in bboxes),
    )


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _linked_block_ids(blocks: Iterable[BlockIR]) -> list[str] | None:
    ids = _unique(link.target_block_id for block in blocks for link in block.links)
    return ids or None
