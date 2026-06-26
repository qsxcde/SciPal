from backend.domain.config import settings
from backend.rag.ingestion.metadata import Chunk
from backend.rag.indexing.vector_store import AbstractVectorStore
from backend.rag.retrieval.filters import filter_indexable_chunks


def retrieve_seed_chunks(
    store: AbstractVectorStore,
    question: str,
    k: int | None = None,
    default_k: int | None = None,
) -> list[Chunk]:
    resolved_k = k or default_k or settings.retrieval_top_k
    return filter_indexable_chunks(store.search(question, k=resolved_k))
