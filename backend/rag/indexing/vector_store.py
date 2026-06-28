import faiss
import json
import logging
import numpy as np
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from backend.domain import config
from backend.domain.exceptions import EmbeddingModelUnavailableError
from backend.rag.embedding import create_embed_fn
from backend.rag.embedding.local_embedder import _get_model, _embedding_unavailable_message
from backend.rag.ingestion.metadata import Chunk

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VectorSearchHit:
    chunk: Chunk
    score: float
    rank: int


class AbstractVectorStore(ABC):
    @abstractmethod
    def add_chunks(self, chunks: list[Chunk]) -> None: ...

    @abstractmethod
    def search(self, query: str, k: int = 5) -> list[Chunk]: ...

    @abstractmethod
    def search_with_ranks(self, query: str, k: int = 5) -> list[VectorSearchHit]: ...

    @abstractmethod
    def list_chunks(self) -> list[Chunk]: ...


# Default embedding function — built from the fallback chain (remote → local).
# Exposed as a module-level attribute so integration tests can monkeypatch it.
_default_embed = create_embed_fn()


class FAISSVectorStore(AbstractVectorStore):
    def __init__(
        self,
        embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
        embedding_dim: int | None = None,
    ):
        self._index = faiss.IndexFlatL2(embedding_dim or config.settings.embedding_dim)
        self._chunks: list[Chunk] = []
        self._embed = embed_fn or _default_embed

    def add_chunks(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        start = time.monotonic()
        logger.info("Embedding %d chunks for FAISS index", len(chunks))
        vectors = np.array(self._embed([c.text for c in chunks]), dtype=np.float32)
        if self._index.ntotal == 0:
            if self._index.d != vectors.shape[1]:
                self._index = faiss.IndexFlatL2(vectors.shape[1])
        elif vectors.shape[1] != self._index.d:
            raise ValueError(
                f"Embedding dimension mismatch: got {vectors.shape[1]}, "
                f"expected {self._index.d}. "
                "This usually means the embedding model changed. "
                "Rebuild the index from scratch or revert to the original model."
            )
        self._index.add(vectors)
        self._chunks.extend(chunks)
        logger.info(
            "Added %d vectors to FAISS index total_vectors=%d dimension=%d elapsed=%.2fs",
            len(chunks),
            self._index.ntotal,
            self._index.d,
            time.monotonic() - start,
        )

    def search(self, query: str, k: int = 5) -> list[Chunk]:
        return [hit.chunk for hit in self.search_with_ranks(query, k=k)]

    def search_with_ranks(self, query: str, k: int = 5) -> list[VectorSearchHit]:
        if self._index.ntotal == 0:
            return []
        query_vec = np.array(self._embed([query]), dtype=np.float32)
        distances, indices = self._index.search(query_vec, min(k, self._index.ntotal))
        hits: list[VectorSearchHit] = []
        for rank, (distance, chunk_index) in enumerate(
            zip(distances[0], indices[0], strict=True),
            start=1,
        ):
            if chunk_index < 0:
                continue
            hits.append(
                VectorSearchHit(
                    chunk=self._chunks[chunk_index],
                    score=float(distance),
                    rank=rank,
                )
            )
        return hits

    def list_chunks(self) -> list[Chunk]:
        return list(self._chunks)

    @property
    def chunks(self) -> list[Chunk]:
        return list(self._chunks)

    def save(self, index_path: Path, chunks_path: Path) -> None:
        start = time.monotonic()
        index_path.parent.mkdir(parents=True, exist_ok=True)
        chunks_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_index = index_path.with_suffix(index_path.suffix + ".tmp")
        tmp_chunks = chunks_path.with_suffix(chunks_path.suffix + ".tmp")
        try:
            faiss.write_index(self._index, str(tmp_index))
            chunks_payload = [chunk.model_dump() for chunk in self._chunks]
            tmp_chunks.write_text(
                json.dumps(chunks_payload, ensure_ascii=False), encoding="utf-8"
            )
            os.replace(str(tmp_index), str(index_path))
            os.replace(str(tmp_chunks), str(chunks_path))
        finally:
            tmp_index.unlink(missing_ok=True)
            tmp_chunks.unlink(missing_ok=True)
        logger.info(
            "Saved FAISS index path=%s total_vectors=%d dimension=%d chunks=%d bytes=%d elapsed=%.2fs",
            index_path,
            self._index.ntotal,
            self._index.d,
            len(self._chunks),
            index_path.stat().st_size,
            time.monotonic() - start,
        )

    def ensure_ready(self) -> None:
        if _get_model() is None:
            raise EmbeddingModelUnavailableError(_embedding_unavailable_message())

    @classmethod
    def load(
        cls,
        index_path: Path,
        chunks_path: Path,
        embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
    ) -> "FAISSVectorStore":
        if not index_path.exists():
            raise FileNotFoundError(f"FAISS index file not found: {index_path}")
        if not chunks_path.exists():
            raise FileNotFoundError(f"FAISS chunks file not found: {chunks_path}")
        store = cls(embed_fn=embed_fn)
        store._index = faiss.read_index(str(index_path))
        payload = json.loads(chunks_path.read_text(encoding="utf-8"))
        store._chunks = [Chunk.model_validate(item) for item in payload]
        stored_vectors = store._index.ntotal
        if stored_vectors != len(store._chunks):
            logger.warning(
                "FAISS index vector count (%d) differs from chunks count (%d). "
                "Index may be corrupted.",
                stored_vectors, len(store._chunks),
            )
        return store
