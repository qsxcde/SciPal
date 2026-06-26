from backend.rag.ingestion.document_ir import BlockIR, BBox, QualityReport
from backend.rag.ingestion.reading_order import is_page_margin_block


def build_quality_report(
    parser_backend,
    page_count: int,
    blocks: list[BlockIR],
    parser_warnings: list[str] | None = None,
) -> QualityReport:
    warnings: list[str] = list(parser_warnings or [])
    heading_count = sum(1 for block in blocks if block.type in {"heading", "title"})
    low_confidence_count = sum(1 for block in blocks if block.confidence < 0.5)
    filtered_header_footer_count = sum(1 for block in blocks if block.type == "header_footer")
    if heading_count == 0:
        warnings.append("NO_HEADINGS_DETECTED")
    if not blocks:
        warnings.append("LOW_TEXT_DENSITY")
    if not blocks and heading_count == 0:
        status = "failed"
    elif not blocks or heading_count == 0:
        status = "poor"
    else:
        status = "good"
    if warnings and status == "good":
        status = "usable_with_warnings"
    return QualityReport(
        parser_name=parser_backend.name,
        parser_version=parser_backend.version,
        page_count=page_count,
        text_block_count=sum(1 for block in blocks if block.type == "paragraph"),
        heading_count=heading_count,
        table_count=sum(1 for block in blocks if block.type == "table"),
        figure_caption_count=sum(1 for block in blocks if block.type == "figure_caption"),
        table_caption_count=sum(1 for block in blocks if block.type == "table_caption"),
        formula_block_count=sum(1 for block in blocks if block.type == "formula"),
        filtered_header_footer_count=filtered_header_footer_count,
        low_confidence_block_count=low_confidence_count,
        warnings=warnings,
        overall_status=status,
    )


def find_repeated_header_footer_texts(pages: list[dict], bbox_model) -> set[str]:
    repeated: dict[str, int] = {}
    for page_data in pages:
        page_height = float(page_data.get("height", 0.0))
        seen_on_page: set[str] = set()
        for block in page_data.get("blocks", []):
            text = str(block.get("text", "")).strip()
            if not text:
                continue
            bbox = bbox_model(block.get("bbox"))
            if not is_page_margin_block(bbox, page_height):
                continue
            if text in seen_on_page:
                continue
            seen_on_page.add(text)
            repeated[text] = repeated.get(text, 0) + 1
    return {text for text, count in repeated.items() if count >= 2}
