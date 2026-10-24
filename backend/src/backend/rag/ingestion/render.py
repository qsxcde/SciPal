"""Single source of truth for turning DocumentIR blocks into text.

Both chunk text and exported Markdown go through :func:`render_block`, so the
indexed content and the preview can never drift apart.
"""

from backend.rag.ingestion.document_ir import BlockIR, DocumentIR


def ordered_blocks(document: DocumentIR) -> list[BlockIR]:
    """Return blocks in deterministic reading order."""
    blocks = document.blocks or [block for page in document.pages for block in page.blocks]
    return sorted(blocks, key=lambda block: (block.page_number, block.reading_order, block.block_index))


def render_block(block: BlockIR) -> str:
    """Render one block as plain text or Markdown."""
    text = block.text.strip()
    if block.type == "title":
        return f"# {text}" if text else ""
    if block.type == "heading":
        return f"## {text}" if text else ""
    if block.type == "table":
        return f"[Table on page {block.page_number}]\n{text}" if text else f"[Table on page {block.page_number}]"
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
