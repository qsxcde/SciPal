from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from backend.rag.ingestion.metadata import Chunk
from backend.rag.indexing.vector_store import AbstractVectorStore
from backend.rag.retrieval.bm25 import BM25Retriever
from backend.rag.retrieval.context_builder import expand_context_with_debug
from backend.rag.retrieval.filters import filter_indexable_chunks
from backend.rag.retrieval.fusion import RetrievalHit, reciprocal_rank_fusion
from backend.rag.retrieval.language import Language, detect_language, infer_document_language
from backend.rag.retrieval.query_rewriter import QueryPack, generate_query_pack

logger = logging.getLogger(__name__)
_bm25_cache: dict[str, tuple[str, BM25Retriever]] = {}
_bm25_cache_lock = threading.Lock()


def _bm25_fingerprint(chunks: list[Chunk]) -> str:
    """Compute a stable fingerprint for a list of chunks."""
    h = hashlib.md5()
    for c in chunks:
        h.update(f"{c.metadata.paper_id}:{c.metadata.chunk_index}:{c.metadata.section}\n".encode())
    return h.hexdigest()


def _get_bm25_retriever(chunks: list[Chunk]) -> BM25Retriever:
    """Get or create a cached BM25Retriever for the given chunks."""
    fp = _bm25_fingerprint(chunks)
    with _bm25_cache_lock:
        cached = _bm25_cache.get("default")
        if cached is not None and cached[0] == fp:
            return cached[1]
        retriever = BM25Retriever(chunks)
        _bm25_cache["default"] = (fp, retriever)
    logger.debug("Built new BM25Retriever fingerprint=%s chunks=%d", fp, len(chunks))
    return retriever


@dataclass(frozen=True)
class HybridRetrievalOptions:
    bm25_top_k: int = 5
    dense_top_k: int = 5
    seed_top_k: int = 5
    max_expanded_chunks: int = 8
    same_section_window: int = 0
    adjacent_window: int = 1
    include_linked_blocks: bool = False
    rrf_k: int = 60
    enable_reranker: bool = True
    rerank_top_k: int = 8


@dataclass(frozen=True)
class RetrievalRoute:
    query_language: Language
    document_language: Language
    used_query_pack: bool
    dense_used_ranked_hits: bool


@dataclass(frozen=True)
class HybridRetrievalResult:
    route: RetrievalRoute
    ranked_chunks: list[Chunk]
    prompt_chunks: list[Chunk]
    ranked_debug: list[dict[str, object]] = field(default_factory=list)
    expansion_debug: list[dict[str, object]] = field(default_factory=list)


def retrieve_hybrid_context(
    store: AbstractVectorStore,
    query: str,
    *,
    options: HybridRetrievalOptions | None = None,
    query_pack_factory: Callable[[str, str, str], QueryPack] | None = None,
) -> HybridRetrievalResult:
    retrieval_options = options or HybridRetrievalOptions()
    all_chunks = filter_indexable_chunks(store.list_chunks())
    query_language = detect_language(query).language
    document_language = infer_document_language(all_chunks)

    used_query_pack = query_language != document_language
    dense_query = query
    bm25_query = query
    if used_query_pack:
        factory = query_pack_factory or generate_query_pack
        pack = factory(query, query_language, document_language)
        dense_query = pack.retrieval_query
        bm25_query = " ".join([pack.translated_query, *pack.keywords]).strip()

    bm25 = _get_bm25_retriever(all_chunks)
    bm25_hits = [
        RetrievalHit(chunk=hit.chunk, score=hit.score, rank=hit.rank)
        for hit in bm25.search(bm25_query, k=retrieval_options.bm25_top_k)
    ]
    if retrieval_options.dense_top_k > 0:
        dense_hits, dense_used_ranked_hits = _collect_dense_hits(
            store,
            dense_query,
            retrieval_options.dense_top_k,
        )
    else:
        dense_hits, dense_used_ranked_hits = [], False
    ranked_candidates = reciprocal_rank_fusion(
        {"bm25": bm25_hits, "dense": dense_hits},
        top_k=retrieval_options.seed_top_k,
        rrf_k=retrieval_options.rrf_k,
    )
    ranked_chunks = [candidate.chunk for candidate in ranked_candidates]

    if retrieval_options.enable_reranker and retrieval_options.rerank_top_k > 0:
        from backend.rag.retrieval import reranker as _reranker_mod
        reranker = _reranker_mod.get_reranker()
        if reranker is not None:
            rerank_start = time.monotonic()
            reranked = reranker.rerank(dense_query, ranked_chunks, top_k=retrieval_options.rerank_top_k)
            if reranked:
                logger.info(
                    "Reranked %d chunks to %d elapsed=%.2fs",
                    len(ranked_chunks), len(reranked), time.monotonic() - rerank_start,
                )
                ranked_chunks = reranked

    prompt_chunks, expansion_debug = _expand_prompt_chunks(
        ranked_chunks,
        all_chunks,
        max_chunks=retrieval_options.max_expanded_chunks,
        same_section_window=retrieval_options.same_section_window,
        adjacent_window=retrieval_options.adjacent_window,
        include_linked_blocks=retrieval_options.include_linked_blocks,
    )

    return HybridRetrievalResult(
        route=RetrievalRoute(
            query_language=query_language,
            document_language=document_language,
            used_query_pack=used_query_pack,
            dense_used_ranked_hits=dense_used_ranked_hits,
        ),
        ranked_chunks=ranked_chunks,
        prompt_chunks=prompt_chunks,
        ranked_debug=[candidate.to_debug_dict() for candidate in ranked_candidates],
        expansion_debug=expansion_debug,
    )


def _collect_dense_hits(
    store: AbstractVectorStore,
    query: str,
    k: int,
) -> tuple[list[RetrievalHit], bool]:
    search_with_ranks = getattr(store, "search_with_ranks", None)
    if search_with_ranks is not None:
        try:
            ranked_hits = search_with_ranks(query, k=k)
        except NotImplementedError:
            ranked_hits = None
        else:
            return (
                [RetrievalHit(chunk=hit.chunk, score=hit.score, rank=hit.rank) for hit in ranked_hits],
                True,
            )
    chunks = store.search(query, k=k)
    return (
        [RetrievalHit(chunk=chunk, score=0.0, rank=rank) for rank, chunk in enumerate(chunks, start=1)],
        False,
    )


def _expand_prompt_chunks(
    seed_chunks: list[Chunk],
    all_chunks: list[Chunk],
    *,
    max_chunks: int,
    same_section_window: int,
    adjacent_window: int,
    include_linked_blocks: bool,
) -> tuple[list[Chunk], list[dict[str, object]]]:
    return expand_context_with_debug(
        seed_chunks=seed_chunks,
        all_chunks=all_chunks,
        max_chunks=max_chunks,
        same_section_window=same_section_window,
        adjacent_window=adjacent_window,
        include_linked_blocks=include_linked_blocks,
    )
