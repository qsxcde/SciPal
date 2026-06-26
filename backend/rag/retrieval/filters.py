from backend.rag.ingestion.metadata import Chunk


REFERENCE_SECTION_NAMES = {
    "references", "reference", "bibliography", "参考文献",
    "literaturverzeichnis", "bibliographie", "referencias",
    "참고문헌", "参考文獻",
}


def is_reference_chunk(chunk: Chunk) -> bool:
    """Return whether a chunk belongs to the paper bibliography section."""
    if chunk.metadata.is_reference:
        return True
    labels = [chunk.metadata.section, *(chunk.metadata.section_path or [])]
    return any(_normalize_section_label(label) in REFERENCE_SECTION_NAMES for label in labels)


def filter_indexable_chunks(chunks: list[Chunk]) -> list[Chunk]:
    """Keep chunks that should participate in default paper QA retrieval."""
    return [chunk for chunk in chunks if not is_reference_chunk(chunk)]


def _normalize_section_label(label: str | None) -> str:
    if label is None:
        return ""
    normalized = " ".join(label.strip().lower().split())
    while normalized and (normalized[0].isdigit() or normalized[0] in ".、)）"):
        normalized = normalized[1:].strip()
    return normalized
