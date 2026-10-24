"""Chunk text and exported Markdown share one renderer."""

import pytest

from backend.rag.ingestion.document_ir import BBox, BlockIR, DocumentIR, PageIR, QualityReport
from backend.rag.ingestion.render import ordered_blocks, render_block


def _block(block_type, text, *, page=1, order=0, index=0, section_path=None) -> BlockIR:
    return BlockIR(
        id=f"b-{page}-{index}",
        page_number=page,
        block_index=index,
        type=block_type,
        text=text,
        bbox=BBox(x0=0, y0=0, x1=1, y1=1),
        reading_order=order,
        section_path=section_path or [],
    )


def _document(*blocks: BlockIR) -> DocumentIR:
    return DocumentIR(
        document_id="doc-1",
        filename="paper.pdf",
        page_count=1,
        parser_name="test",
        parser_version="1",
        pages=[PageIR(page_number=1, width=1, height=1, rotation=0, blocks=list(blocks))],
        quality_report=QualityReport(parser_name="test", parser_version="1", page_count=1),
    )


@pytest.mark.unit
def test_ordered_blocks_sorts_by_page_order_index():
    second = _block("paragraph", "second", page=2, order=0, index=0)
    first = _block("paragraph", "first", page=1, order=5, index=1)
    earlier = _block("paragraph", "earlier", page=1, order=1, index=9)

    ordered = ordered_blocks(_document(second, first, earlier))

    assert [block.text for block in ordered] == ["earlier", "first", "second"]


@pytest.mark.unit
def test_render_block_handles_structure_types():
    assert render_block(_block("title", "SciPal")) == "# SciPal"
    assert render_block(_block("heading", "Intro")) == "## Intro"
    assert render_block(_block("table", "| a |")) == "[Table on page 1]\n| a |"
    assert render_block(_block("table", "")) == "[Table on page 1]"
    assert render_block(_block("figure_caption", "Fig 1")) == "**Figure:** Fig 1"
    assert render_block(_block("table_caption", "Tab 1")) == "**Table:** Tab 1"
    assert render_block(_block("paragraph", "body")) == "body"


@pytest.mark.unit
def test_render_block_falls_back_for_empty_formula():
    block = _block("formula", "", section_path=["3", "Method"])

    assert render_block(block) == "[Formula on page 1 near 3 > Method]"


@pytest.mark.unit
def test_chunk_text_and_markdown_agree_on_rendering():
    from backend.rag.ingestion.chunking import build_chunks

    blocks = [
        _block("title", "SciPal", order=0),
        _block("paragraph", "First paragraph.", order=1, index=1, section_path=["1"]),
        _block("table", "| a | b |", order=2, index=2, section_path=["2"]),
    ]
    document = _document(*blocks)

    chunk_text = "\n\n".join(chunk.text for chunk in build_chunks(document, "", "doc-1"))

    assert "[Table on page 1]\n| a | b |" in chunk_text
    assert "# SciPal" not in chunk_text  # titles are skipped by chunking, not mangled
