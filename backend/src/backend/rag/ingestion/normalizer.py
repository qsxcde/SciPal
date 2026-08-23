import logging

from backend.rag.ingestion.document_ir import BBox, BlockIR, DocumentIR, PageIR
from backend.rag.ingestion.document_ir import BlockLink
from backend.rag.ingestion.block_classifier import clean_heading, confidence_for_type, detect_block_type
from backend.rag.ingestion.linker import attach_caption_links
from backend.rag.ingestion.parser_backend import ParserBackend, RawParserResult
from backend.rag.ingestion.quality_reporter import build_quality_report, find_repeated_header_footer_texts
from backend.rag.ingestion.reading_order import bbox_tuple, sorted_blocks_for_reading_order

logger = logging.getLogger(__name__)
from backend.rag.ingestion.section_builder import next_section_path, outline_from_blocks


def normalize_parser_output(
    raw: RawParserResult,
    paper_id: str,
    filename: str,
    parser_backend: ParserBackend,
) -> DocumentIR:
    """Normalize parser-specific output into the stable DocumentIR contract."""
    pages: list[PageIR] = []
    all_blocks: list[BlockIR] = []
    current_section: list[str] = ["Abstract"]
    in_references = False
    reading_order = 0
    repeated_header_footer_texts = find_repeated_header_footer_texts(raw.pages, _bbox_model)

    for page_data in raw.pages:
        page_number = int(page_data.get("page_number", len(pages) + 1))
        page_width = float(page_data.get("width", 0.0))
        page_height = float(page_data.get("height", 0.0))
        page_blocks: list[BlockIR] = []
        raw_blocks = page_data.get("blocks", [])
        for index, block_data in enumerate(raw_blocks):
            block_data["_original_index"] = index
        sorted_blocks = sorted_blocks_for_reading_order(raw_blocks, page_width, _bbox_model)
        for block_data in sorted_blocks:
            text = str(block_data.get("text", "")).strip()
            if not text and str(block_data.get("type", "")).strip().lower() not in {"formula"}:
                continue
            bbox = _bbox_model(block_data.get("bbox"))
            if not text and bbox.x0 == 0.0 and bbox.x1 == 0.0 and bbox.y0 == 0.0 and bbox.y1 == 0.0:
                logger.warning(
                    "Empty block at p%d with zero bbox, type=%s; skipping",
                    page_number, block_data.get("type"),
                )
                continue
            block_type = _resolve_block_type(
                block_data=block_data,
                text=text,
                bbox=bbox,
                page_height=page_height,
                repeated_header_footer_texts=repeated_header_footer_texts,
                in_references=in_references,
            )
            if block_type == "unknown" and not text:
                continue
            if _is_visual_only_block(block_data, block_type):
                continue
            if block_type == "heading":
                current_section = next_section_path(current_section, text)
                cleaned_text = clean_heading(text)
                heading_lower = cleaned_text.lower()
                if heading_lower == "references":
                    in_references = True
                elif in_references and _is_post_reference_heading(heading_lower):
                    in_references = False
            elif block_type == "reference":
                current_section = ["References"]
                in_references = True
                cleaned_text = text
            elif block_type == "header_footer":
                cleaned_text = text
            else:
                cleaned_text = text
            block = BlockIR(
                id=f"p{page_number}-ro{reading_order}",
                page_number=page_number,
                block_index=int(block_data.pop("_original_index", reading_order)),
                type=block_type,
                text=cleaned_text,
                bbox=bbox,
                reading_order=reading_order,
                section_path=current_section.copy() if block_type != "header_footer" else [],
                confidence=_resolve_confidence(block_data, block_type, cleaned_text),
                links=_resolve_links(block_data),
            )
            reading_order += 1
            page_blocks.append(block)
            all_blocks.append(block)
        attach_caption_links(page_blocks)
        pages.append(
            PageIR(
                page_number=page_number,
                width=page_width,
                height=float(page_data.get("height", 0.0)),
                rotation=int(page_data.get("rotation", 0)),
                blocks=page_blocks,
            )
        )

    quality_report = build_quality_report(
        parser_backend=parser_backend,
        page_count=raw.page_count,
        blocks=all_blocks,
        parser_warnings=raw.warnings,
    )
    return DocumentIR(
        document_id=paper_id,
        filename=filename,
        page_count=raw.page_count,
        parser_name=parser_backend.name,
        parser_version=parser_backend.version,
        pages=pages,
        blocks=all_blocks,
        outline=outline_from_blocks(all_blocks),
        quality_report=quality_report,
    )


def _bbox_tuple(value: object) -> tuple[float, float, float, float]:
    if isinstance(value, (list, tuple)) and len(value) >= 4:
        return (float(value[0]), float(value[1]), float(value[2]), float(value[3]))
    return (0.0, 0.0, 0.0, 0.0)


def _bbox_model(value: object) -> BBox:
    x0, y0, x1, y1 = bbox_tuple(value)
    return BBox(x0=x0, y0=y0, x1=x1, y1=y1)


def _resolve_block_type(
    block_data: dict,
    text: str,
    bbox: BBox,
    page_height: float,
    repeated_header_footer_texts: set[str],
    in_references: bool,
) -> str:
    raw_type = str(block_data.get("type", "")).strip().lower()
    if raw_type in {
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
    }:
        return raw_type
    return detect_block_type(
        text=text,
        bbox=bbox,
        page_height=page_height,
        repeated_header_footer_texts=repeated_header_footer_texts,
        in_references=in_references,
    )


def _resolve_confidence(block_data: dict, block_type: str, text: str) -> float:
    raw_confidence = block_data.get("confidence")
    if raw_confidence is not None:
        try:
            return float(raw_confidence)
        except (TypeError, ValueError):
            pass
    return confidence_for_type(block_type, text)


def _resolve_links(block_data: dict) -> list[BlockLink]:
    links: list[BlockLink] = []
    for item in block_data.get("links", []) or []:
        if not isinstance(item, dict):
            continue
        target_block_id = str(item.get("target_block_id", "")).strip()
        relation = str(item.get("relation", "")).strip()
        if not target_block_id or not relation:
            continue
        links.append(BlockLink(target_block_id=target_block_id, relation=relation))
    return links


def _is_visual_only_block(block_data: dict, block_type: str) -> bool:
    raw_type = str(block_data.get("type", "")).strip().lower()
    return raw_type in {"image", "figure", "picture"} and block_type not in {"figure_caption", "table_caption"}


def _is_post_reference_heading(heading_lower: str) -> bool:
    return heading_lower in {
        "appendix", "appendices", "supplementary", "supplementary material",
        "acknowledgments", "acknowledgements",
    } or heading_lower.startswith("appendix") or heading_lower.startswith("supplementary")
