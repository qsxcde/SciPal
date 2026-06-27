from functools import cache
from pathlib import Path
import tomllib

from backend.rag.ingestion.metadata import Chunk

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


@cache
def _load_prompts() -> dict:
    path = _PROMPTS_DIR / "prompts.toml"
    with open(path, "rb") as f:
        return tomllib.load(f)


_root = _load_prompts()["rag_answer"]
SYSTEM_PROMPT = _root["system"]


def build_prompt(
    chunks: list[Chunk],
    question: str,
    *,
    context_token_budget: int | None = None,
) -> str:
    selected_chunks = _select_chunks_within_budget(chunks, context_token_budget)
    context = "\n\n---\n\n".join(_format_chunk_for_prompt(chunk) for chunk in selected_chunks)
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


def _select_chunks_within_budget(
    chunks: list[Chunk],
    context_token_budget: int | None = None,
) -> list[Chunk]:
    if context_token_budget is None:
        return chunks

    selected_chunks: list[Chunk] = []
    remaining_budget = max(context_token_budget, 0)

    for chunk in chunks:
        header = _format_chunk_header(chunk)
        header_cost = _estimate_tokens(header) + _estimate_tokens("\n")
        if remaining_budget <= 0 and selected_chunks:
            break

        if header_cost >= remaining_budget:
            if not selected_chunks:
                selected_chunks.append(
                    chunk.model_copy(
                        update={"text": _truncate_text_to_token_budget(chunk.text, 1)}
                    )
                )
            break

        available_text_budget = remaining_budget - header_cost
        truncated_text = _truncate_text_to_token_budget(chunk.text, available_text_budget)
        text_cost = _estimate_tokens(truncated_text)
        selected_chunks.append(chunk.model_copy(update={"text": truncated_text}))
        remaining_budget -= header_cost + text_cost

        if text_cost < _estimate_tokens(chunk.text):
            break

    return selected_chunks


def _truncate_text_to_token_budget(text: str, token_budget: int) -> str:
    if token_budget <= 0:
        return ""

    max_chars = token_budget * 4
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return (len(text) + 1) // 2


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
