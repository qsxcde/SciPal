from dataclasses import asdict, is_dataclass
import re
from typing import Generator, Literal, TypedDict

from pydantic import BaseModel, Field

from backend.rag.generation.answer_generator import build_sources
from backend.rag.generation.answer_generator import generate_answer
from backend.rag.generation.answer_generator import stream_answer as stream_answer_for_chunks
from backend.rag.generation.prompt_template import build_prompt
from backend.rag.ingestion.metadata import Chunk, SourceRef
from backend.rag.indexing.vector_store import AbstractVectorStore
from backend.rag.retrieval.context_builder import expand_context
from backend.rag.retrieval.hybrid_retriever import HybridRetrievalOptions
from backend.rag.retrieval.hybrid_retriever import retrieve_hybrid_context
from backend.rag.retrieval.retriever import retrieve_seed_chunks

MAX_EXPANDED_CHUNKS = 8
SAME_SECTION_WINDOW = 1
ADJACENT_WINDOW = 1
EMPTY_RETRIEVAL_REFUSAL_TEXT = "未在当前检索结果中找到可支持该问题的论文依据。"
CITATION_PATTERN = re.compile(r"\[Chunk:\s*(\d+)\]")


class StreamTokenEvent(TypedDict):
    type: Literal["token"]
    value: str


class StreamSourcesEvent(TypedDict):
    type: Literal["sources"]
    value: list[SourceRef]


class StreamWarningEvent(TypedDict):
    type: Literal["warning"]
    value: str


StreamAnswerEvent = StreamTokenEvent | StreamSourcesEvent | StreamWarningEvent


class ChatEvaluationResult(BaseModel):
    answer: str
    retrieved_chunks: list[Chunk]
    sources: list[SourceRef]
    retrieval_mode: str = "live"
    generation_mode: str = "live"
    warning: str = ""
    ranked_chunks: list[Chunk] = Field(default_factory=list)
    retrieval_debug: dict[str, object] = Field(default_factory=dict)


class RetrievalOptions(BaseModel):
    strategy: Literal["dense", "bm25", "hybrid"] = "dense"
    max_expanded_chunks: int = MAX_EXPANDED_CHUNKS
    same_section_window: int = SAME_SECTION_WINDOW
    adjacent_window: int = ADJACENT_WINDOW
    include_linked_blocks: bool = True
    bm25_top_k: int = 5
    dense_top_k: int = 5
    seed_top_k: int = 5
    rrf_k: int = 60


class RetrievalDiagnostics(BaseModel):
    ranked_chunks: list[Chunk] = Field(default_factory=list)
    route: dict[str, object] = Field(default_factory=dict)
    ranked_debug: list[dict[str, object]] = Field(default_factory=list)
    expansion_debug: list[dict[str, object]] = Field(default_factory=list)


def retrieve_context(
    store: AbstractVectorStore,
    query: str,
    k: int | None = None,
    options: RetrievalOptions | None = None,
    include_diagnostics: bool = False,
) -> tuple[list[Chunk], list[SourceRef]] | tuple[list[Chunk], list[SourceRef], RetrievalDiagnostics]:
    retrieval_options = options or RetrievalOptions()
    if retrieval_options.strategy in {"bm25", "hybrid"}:
        hybrid_result = retrieve_hybrid_context(
            store,
            query,
            options=HybridRetrievalOptions(
                bm25_top_k=retrieval_options.bm25_top_k,
                dense_top_k=0 if retrieval_options.strategy == "bm25" else retrieval_options.dense_top_k,
                seed_top_k=retrieval_options.seed_top_k,
                max_expanded_chunks=retrieval_options.max_expanded_chunks,
                same_section_window=retrieval_options.same_section_window,
                adjacent_window=retrieval_options.adjacent_window,
                include_linked_blocks=retrieval_options.include_linked_blocks,
                rrf_k=retrieval_options.rrf_k,
            ),
        )
        sources = build_sources(hybrid_result.prompt_chunks)
        diagnostics = RetrievalDiagnostics(
            ranked_chunks=hybrid_result.ranked_chunks,
            route=_serialize_route(hybrid_result.route),
            ranked_debug=hybrid_result.ranked_debug,
            expansion_debug=hybrid_result.expansion_debug,
        )
        if include_diagnostics:
            return hybrid_result.prompt_chunks, sources, diagnostics
        return hybrid_result.prompt_chunks, sources

    seed_chunks = retrieve_seed_chunks(store, query, k=k)
    chunks = expand_context(
        seed_chunks=seed_chunks,
        all_chunks=store.list_chunks(),
        max_chunks=retrieval_options.max_expanded_chunks,
        same_section_window=retrieval_options.same_section_window,
        adjacent_window=retrieval_options.adjacent_window,
        include_linked_blocks=retrieval_options.include_linked_blocks,
    )
    sources = build_sources(chunks)
    diagnostics = RetrievalDiagnostics(ranked_chunks=seed_chunks)
    if include_diagnostics:
        return chunks, sources, diagnostics
    return chunks, sources


def stream_answer(
    store: AbstractVectorStore,
    query: str,
    options: RetrievalOptions | None = None,
) -> Generator[StreamAnswerEvent, None, None]:
    chunks, sources = retrieve_context(store, query, options=options)
    if not chunks:
        yield {"type": "token", "value": EMPTY_RETRIEVAL_REFUSAL_TEXT}
        yield {"type": "sources", "value": []}
        return
    token_stream = stream_answer_for_chunks(chunks, query)
    buffered_tokens: list[str] = []
    try:
        while True:
            token = next(token_stream)
            buffered_tokens.append(token)
            yield {"type": "token", "value": token}
    except StopIteration as stop:
        streamed_sources = stop.value

    answer = "".join(buffered_tokens)
    has_valid_citations = _answer_has_valid_chunk_citations(answer, chunks)
    if not has_valid_citations:
        streamed_sources = []

    yield {"type": "sources", "value": streamed_sources}
    if not has_valid_citations:
        yield {"type": "warning", "value": "模型生成的回答中未引用有效论文来源，请核实。"}


def evaluate_answer(
    store: AbstractVectorStore,
    query: str,
    k: int | None = None,
    options: RetrievalOptions | None = None,
) -> ChatEvaluationResult:
    chunks, sources, diagnostics = retrieve_context(
        store,
        query,
        k=k,
        options=options,
        include_diagnostics=True,
    )
    if not chunks:
        answer = EMPTY_RETRIEVAL_REFUSAL_TEXT
    else:
        generated_answer = generate_answer(chunks, query)
        answer = (
            generated_answer
            if _answer_has_valid_chunk_citations(generated_answer, chunks)
            else EMPTY_RETRIEVAL_REFUSAL_TEXT
        )
    return ChatEvaluationResult(
        answer=answer,
        retrieved_chunks=chunks,
        sources=sources,
        generation_mode="skipped" if not chunks else "live",
        ranked_chunks=diagnostics.ranked_chunks,
        retrieval_debug={
            "route": diagnostics.route,
            "ranked_debug": diagnostics.ranked_debug,
            "expansion_debug": diagnostics.expansion_debug,
        },
    )


def evaluate_retrieval(
    store: AbstractVectorStore,
    query: str,
    k: int | None = None,
    options: RetrievalOptions | None = None,
) -> ChatEvaluationResult:
    chunks, sources, diagnostics = retrieve_context(
        store,
        query,
        k=k,
        options=options,
        include_diagnostics=True,
    )
    return ChatEvaluationResult(
        answer="",
        retrieved_chunks=chunks,
        sources=sources,
        generation_mode="skipped",
        ranked_chunks=diagnostics.ranked_chunks,
        retrieval_debug={
            "route": diagnostics.route,
            "ranked_debug": diagnostics.ranked_debug,
            "expansion_debug": diagnostics.expansion_debug,
        },
    )

def _serialize_route(route: object) -> dict[str, object]:
    if is_dataclass(route):
        return asdict(route)
    if hasattr(route, "__dict__"):
        return dict(vars(route))
    return {}


def _answer_has_valid_chunk_citations(answer: str, retrieved_chunks: list[Chunk]) -> bool:
    valid_chunk_ids = {chunk.metadata.chunk_index for chunk in retrieved_chunks}
    cited_chunk_ids = {int(match) for match in CITATION_PATTERN.findall(answer)}
    return bool(cited_chunk_ids) and cited_chunk_ids.issubset(valid_chunk_ids)
