"""Local SentenceTransformer-based embedding (fallback)."""
import logging
import os
import threading
import time
from pathlib import Path

import torch
from modelscope import snapshot_download
from sentence_transformers import SentenceTransformer

from backend.domain import config
from backend.domain.exceptions import EmbeddingModelUnavailableError

logger = logging.getLogger(__name__)

MAX_EMBEDDING_WORDS = 220
MAX_EMBEDDING_CHARS = 1600

_MODEL_RETRY_BASE_INTERVAL = 60.0
_MODEL_RETRY_MAX_INTERVAL = 600.0

_model: SentenceTransformer | None = None
_model_load_failed_at: float | None = None
_model_load_error_message = ""
_model_retry_interval = _MODEL_RETRY_BASE_INTERVAL
_model_lock = threading.Lock()


def embed(texts: list[str]) -> list[list[float]]:
    """Embed texts using the local SentenceTransformer model."""
    model = _get_model()
    if model is None:
        raise EmbeddingModelUnavailableError(_embedding_unavailable_message())
    encode_start = time.monotonic()
    logger.info("Encoding %d texts with local embedding model", len(texts))
    vectors = model.encode(
        [truncate_for_embedding(text) for text in texts],
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    rows = [vector.tolist() for vector in vectors]
    dimension = len(rows[0]) if rows else 0
    logger.info(
        "Encoded %d texts with local embedding model dimension=%d elapsed=%.2fs",
        len(rows),
        dimension,
        time.monotonic() - encode_start,
    )
    return rows


def truncate_for_embedding(text: str) -> str:
    words = text.split()
    if len(words) > MAX_EMBEDDING_WORDS:
        text = " ".join(words[:MAX_EMBEDDING_WORDS])
    if len(text) > MAX_EMBEDDING_CHARS:
        text = text[:MAX_EMBEDDING_CHARS]
    return text


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
