"""Production wiring of capability parameters and user-facing wording.

This is the single place where deployment settings are translated into the
configuration-free objects consumed by ``backend.rag``.
"""

from pathlib import Path

from backend.config import backend_project_dir, settings
from backend.rag.answer import AnswerPolicy, RetrievalOptions


def _glossary_path() -> str:
    """Resolve the term glossary path once, so RAG never has to."""
    raw = Path(settings.term_expand_glossary_path)
    if raw.is_absolute():
        return str(raw)
    return str(backend_project_dir().parent / raw)


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
        history_rewrite_min_query_length=settings.history_rewrite_min_query_length,
        term_expand_enabled=settings.term_expand_enabled,
        term_expand_llm_fallback=settings.term_expand_llm_fallback,
        term_glossary_path=_glossary_path(),
    )


def answer_policy() -> AnswerPolicy:
    return AnswerPolicy(
        empty_retrieval_message=settings.msg_empty_retrieval,
        invalid_citation_message=settings.msg_no_valid_citations,
        source_excerpt_max_chars=settings.source_excerpt_max_chars,
    )
