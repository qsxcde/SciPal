from backend.rag.ingestion.document_ir import BlockIR, BlockLink


def attach_caption_links(page_blocks: list[BlockIR]) -> None:
    tables = [block for block in page_blocks if block.type == "table"]
    figures = [
        block for block in page_blocks
        if block.type == "figure_caption" or str(block.type).strip().lower() in {"figure", "image"}
    ]
    for block in page_blocks:
        if block.type == "table_caption":
            linked = _nearest(block, tables)
            if linked is not None:
                block.links.append(BlockLink(target_block_id=linked.id, relation="caption_for"))
        elif block.type == "figure_caption":
            linked = _nearest(block, figures)
            if linked is not None:
                block.links.append(BlockLink(target_block_id=linked.id, relation="caption_for"))


def _nearest(caption: BlockIR, candidates: list[BlockIR]) -> BlockIR | None:
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda c: abs(caption.bbox.y1 - c.bbox.y0) + abs(caption.bbox.x0 - c.bbox.x0),
    )
