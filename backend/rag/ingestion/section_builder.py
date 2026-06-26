from backend.rag.ingestion.document_ir import BlockIR
from backend.rag.ingestion.block_classifier import NUMBERED_HEADING_PATTERN, clean_heading


def next_section_path(current_section: list[str], text: str) -> list[str]:
    cleaned = clean_heading(text)
    match = NUMBERED_HEADING_PATTERN.match(text.strip())
    if not match:
        if len(current_section) > 1:
            return current_section[:-1] + [cleaned]
        return [cleaned]
    level = len(match.group("number").split("."))
    if level <= 1:
        return [cleaned]
    parent = current_section[: level - 1]
    if len(parent) < level - 1:
        parent = parent + ["Unknown"] * ((level - 1) - len(parent))
    return parent + [cleaned]


def outline_from_blocks(blocks: list[BlockIR]) -> list[str]:
    return [block.text for block in blocks if block.type == "heading"]
