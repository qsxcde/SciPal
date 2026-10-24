from backend.rag.ingestion.document_ir import DocumentIR
from backend.rag.ingestion.render import ordered_blocks, render_block


def export_markdown(document: DocumentIR) -> str:
    """Export DocumentIR to deterministic Markdown for cache and preview use."""
    lines: list[str] = []
    for block in ordered_blocks(document):
        if block.type == "header_footer":
            continue
        rendered = render_block(block)
        if rendered:
            lines.append(rendered)
    return "\n\n".join(lines).strip() + "\n"
