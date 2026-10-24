from collections.abc import Generator

from backend.rag.generation.llm import stream_completion_tokens
from backend.rag.generation.prompt_template import build_prompt
from backend.domain.models import Chunk, SourceRef

DEFAULT_SOURCE_EXCERPT_MAX_CHARS = 220


def stream_answer(
    chunks: list[Chunk],
    question: str,
) -> Generator[str, None, list[SourceRef]]:
    prompt = build_prompt(chunks, question)
    for token in stream_completion_tokens(prompt):
        yield token
    return build_sources(chunks)


def generate_answer(chunks: list[Chunk], question: str) -> str:
    return "".join(stream_completion_tokens(build_prompt(chunks, question)))


def build_sources(
    chunks: list[Chunk],
    excerpt_max_chars: int = DEFAULT_SOURCE_EXCERPT_MAX_CHARS,
) -> list[SourceRef]:
    return [
        SourceRef(
            paper_id=chunk.metadata.paper_id,
            section=chunk.metadata.section,
            chunk_index=chunk.metadata.chunk_index,
            text_excerpt=chunk.text[:excerpt_max_chars],
            page_start=chunk.metadata.page_start,
            page_end=chunk.metadata.page_end,
            block_ids=chunk.metadata.block_ids,
            confidence=chunk.metadata.confidence,
        )
        for chunk in chunks
    ]
