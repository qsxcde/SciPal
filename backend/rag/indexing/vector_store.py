import faiss
import json
import logging
import numpy as np
import os
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from modelscope import snapshot_download
from pathlib import Path
from sentence_transformers import SentenceTransformer
from typing import Callable
import torch
from backend.domain.exceptions import EmbeddingModelUnavailableError
from backend.domain import config
from backend.rag.ingestion.metadata import Chunk

MAX_EMBEDDING_WORDS = 220
MAX_EMBEDDING_CHARS = 1600

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

_MODEL_RETRY_BASE_INTERVAL = 60.0
_MODEL_RETRY_MAX_INTERVAL = 600.0

_model: SentenceTransformer | None = None
_model_load_failed_at: float | None = None
_model_load_error_message = ""
_model_retry_interval = _MODEL_RETRY_BASE_INTERVAL
_model_lock = threading.Lock()


def _get_model() -> SentenceTransformer | None:
    global _model, _model_load_failed_at, _model_load_error_message, _model_retry_interval
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        if _model_load_failed_at is not None:
            elapsed = time.monotonic() - _model_load_failed_at
            if elapsed < _model_retry_interval:
                return None
            logger.info(
                "Retrying model load after %.0fs (backoff: %.0fs)",
                elapsed, _model_retry_interval,
            )
            _model_load_failed_at = None
    try:
        _configure_embedding_runtime()
        model_source = _resolve_model_source()
        load_start = time.monotonic()
        logger.info(
            "Loading embedding model source=%s device=%s local_files_only=%s",
            model_source,
            config.settings.embedding_device,
            config.settings.embedding_local_files_only,
        )
        _model = SentenceTransformer(
            model_source,
            local_files_only=config.settings.embedding_local_files_only,
            device=config.settings.embedding_device,
        )
        _model_retry_interval = _MODEL_RETRY_BASE_INTERVAL
        _model_load_failed_at = None
        _model_load_error_message = ""
        logger.info(
            "Loaded embedding model source=%s elapsed=%.2fs",
            model_source,
            time.monotonic() - load_start,
        )
    except Exception as exc:
        _model_load_failed_at = time.monotonic()
        _model_load_error_message = str(exc)
        _model_retry_interval = min(_model_retry_interval * 2, _MODEL_RETRY_MAX_INTERVAL)
        logger.exception("Failed to load embedding model (retry in %.0fs)", _model_retry_interval)
        return None
    return _model


def _default_embed(texts: list[str]) -> list[list[float]]:
    model = _get_model()
    if model is None:
        raise EmbeddingModelUnavailableError(_embedding_unavailable_message())
    encode_start = time.monotonic()
    logger.info("Encoding %d texts with embedding model", len(texts))
    vectors = model.encode(
        [_truncate_for_embedding(text) for text in texts],
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    rows = [vector.tolist() for vector in vectors]
    dimension = len(rows[0]) if rows else 0
    logger.info(
        "Encoded %d texts with embedding model dimension=%d elapsed=%.2fs",
        len(rows),
        dimension,
        time.monotonic() - encode_start,
    )
    return rows


def _truncate_for_embedding(text: str) -> str:
    words = text.split()
    if len(words) > MAX_EMBEDDING_WORDS:
        text = " ".join(words[:MAX_EMBEDDING_WORDS])
    if len(text) > MAX_EMBEDDING_CHARS:
        text = text[:MAX_EMBEDDING_CHARS]
    return text


def _embedding_unavailable_message() -> str:
    model_path = config.embedding_model_dir()
    if _model_load_error_message:
        return (
            "Embedding model is unavailable. "
            f"Expected a local sentence-transformers model at {model_path}. "
            f"Original error: {_model_load_error_message}"
        )
    return (
        "Embedding model is unavailable. "
        f"Expected a local sentence-transformers model at {model_path}."
    )


def _looks_like_complete_model(model_path: Path) -> bool:
    return (
        (model_path / "config.json").is_file()
        and (
            any(model_path.glob("model.safetensors"))
            or any(model_path.glob("pytorch_model.bin"))
            or any(model_path.glob("*.pt"))
        )
    )


def _resolve_model_source() -> str:
    model_path = config.embedding_model_dir()
    if model_path.exists():
        if not _looks_like_complete_model(model_path):
            raise EmbeddingModelUnavailableError(
                f"Embedding model cache at {model_path} appears incomplete "
                "(missing model weights or config). "
                "Delete the directory and re-download, or set a different embedding model."
            )
        return str(model_path)
    if config.settings.embedding_auto_download:
        _download_model_to_path(model_path)
        return str(model_path)
    if config.settings.embedding_local_files_only:
        raise EmbeddingModelUnavailableError(
            f"Local embedding model directory does not exist: {model_path}"
        )
    return config.settings.embedding_model


def _download_model_to_path(model_path: Path) -> None:
    model_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if config.settings.embedding_model_source == "modelscope":
            snapshot_download(
                config.settings.embedding_model,
                cache_dir=str(model_path.parent),
                local_dir=str(model_path),
            )
        elif config.settings.embedding_model_source == "huggingface":
            downloaded_model = SentenceTransformer(
                config.settings.embedding_model,
                cache_folder=str(model_path.parent),
                local_files_only=False,
                device=config.settings.embedding_device,
            )
            downloaded_model.save(str(model_path))
        else:
            raise EmbeddingModelUnavailableError(
                f"Unsupported embedding model source: {config.settings.embedding_model_source}"
            )
        logger.info("Embedding model downloaded to %s", model_path)
    except Exception:
        import shutil
        if model_path.exists():
            shutil.rmtree(model_path)
        raise


def _configure_embedding_runtime() -> None:
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    torch.set_num_threads(1)
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        pass


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
