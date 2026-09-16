from functools import cache
import importlib.resources
import tomllib

from backend.rag.ingestion.metadata import Chunk


@cache
def _load_prompts() -> dict:
    path = importlib.resources.files("backend.prompts") / "prompts.toml"
    with path.open("rb") as f:
        return tomllib.load(f)


_root = _load_prompts()["rag_answer"]
SYSTEM_PROMPT = _root["system"]


def build_prompt(chunks: list[Chunk], question: str) -> str:
    context = "\n\n---\n\n".join(_format_chunk_for_prompt(chunk) for chunk in chunks)
    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"论文片段:\n{context}\n\n"
        f"用户问题: {question}\n\n"
        "请用中文作答。"
    )


def _format_chunk_header(chunk: Chunk) -> str:
    if chunk.metadata.section_path:
        section = " > ".join(s for s in chunk.metadata.section_path if s)
    elif chunk.metadata.section:
        section = chunk.metadata.section
    else:
        section = "Document"
    parts = [f"Section: {section}"]
    page_label = _format_page_range(chunk)
    if page_label:
        parts.append(f"Page: {page_label}")
    parts.append(f"Chunk: {chunk.metadata.chunk_index}")
    if chunk.metadata.confidence is not None and chunk.metadata.confidence < 0.5:
        parts.append("Low confidence source")
    return f"[{' | '.join(parts)}]"


def _format_chunk_for_prompt(chunk: Chunk) -> str:
    return f"{_format_chunk_header(chunk)}\n{chunk.text}"


def _format_page_range(chunk: Chunk) -> str | None:
    start = chunk.metadata.page_start
    end = chunk.metadata.page_end
    if start is None and end is None:
        return None
    if start is None:
        return str(end)
    if end is None or end == start:
        return str(start)
    return f"{start}-{end}"
