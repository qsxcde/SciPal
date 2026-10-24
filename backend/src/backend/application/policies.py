"""Production wiring of capability parameters and user-facing wording.

This is the single place where deployment settings are translated into the
configuration-free objects consumed by ``backend.rag``.
"""

from backend.config import settings
from backend.rag.answer import AnswerPolicy, RetrievalOptions


def retrieval_options() -> RetrievalOptions:
    return RetrievalOptions(
        strategy="hybrid",
        bm25_top_k=settings.bm25_top_k,
        dense_top_k=settings.dense_top_k,
        seed_top_k=settings.seed_top_k,
        rrf_k=settings.rrf_k,
        max_expanded_chunks=settings.max_expanded_chunks,
        same_section_window=settings.same_section_window,
        adjacent_window=settings.adjacent_window,
        include_linked_blocks=settings.include_linked_blocks,
        enable_reranker=settings.reranker_enabled,
        rerank_top_k=settings.rerank_top_k,
        history_rewrite_enabled=settings.history_rewrite_enabled,
        history_rewrite_max_rounds=settings.history_rewrite_max_rounds,
        term_expand_enabled=settings.term_expand_enabled,
    )


def answer_policy() -> AnswerPolicy:
    return AnswerPolicy(
        empty_retrieval_message=settings.msg_empty_retrieval,
        invalid_citation_message=settings.msg_no_valid_citations,
        source_excerpt_max_chars=settings.source_excerpt_max_chars,
    )
