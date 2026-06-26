from backend.rag.ingestion.document_ir import BBox, BlockIR, DocumentIR


def export_markdown(document: DocumentIR) -> str:
    """Export DocumentIR to deterministic Markdown for cache and preview use."""
    lines: list[str] = []
    for block in _ordered_blocks(document):
        if block.type == "header_footer":
            continue
        rendered = _render_block(block)
        if rendered:
            lines.append(rendered)
    return "\n\n".join(lines).strip() + "\n"


def _ordered_blocks(document: DocumentIR) -> list[BlockIR]:
    blocks = document.blocks
    if not blocks:
        blocks = [block for page in document.pages for block in page.blocks]
    return sorted(blocks, key=lambda block: (block.page_number, block.reading_order, block.block_index))


def _render_block(block: BlockIR) -> str:
    text = block.text.strip()
    if block.type == "title":
        return f"# {text}" if text else ""
    if block.type == "heading":
        return f"## {text}" if text else ""
    if block.type == "table":
        return f"[Table on page {block.page_number}]\n{text}" if text else ""
    if block.type == "figure_caption":
        return f"**Figure:** {text}" if text else ""
    if block.type == "table_caption":
        return f"**Table:** {text}" if text else ""
    if block.type == "reference":
        return text
    if block.type == "formula":
        if text:
            return text
        section = " > ".join(block.section_path) if block.section_path else "Document"
        return f"[Formula on page {block.page_number} near {section}]"
    return text


def _merge_bboxes(bboxes: list[BBox]) -> BBox:
    return BBox(
        x0=min(bbox.x0 for bbox in bboxes),
        y0=min(bbox.y0 for bbox in bboxes),
        x1=max(bbox.x1 for bbox in bboxes),
        y1=max(bbox.y1 for bbox in bboxes),
    )
