from __future__ import annotations

import logging
import time
from pathlib import Path

import torch
from modelscope import snapshot_download
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from backend.domain.config import settings
from backend.rag.ingestion.metadata import Chunk

logger = logging.getLogger(__name__)


class FallbackReranker:
    """Reranker that tries remote API first, falls back to local cross-encoder."""

    def __init__(self) -> None:
        self._local: CrossEncoderReranker | None = None

    def rerank(self, query: str, chunks: list[Chunk], top_k: int) -> list[Chunk]:
        if not chunks:
            return []
        if settings.reranker_remote_enabled and settings.embedding_remote_api_key:
            from backend.rag.retrieval import remote_reranker
            remote_result = remote_reranker.rerank(query, chunks, top_k)
            if remote_result is not None:
                return remote_result
        local = self._get_local()
        if local is None:
            return chunks[:top_k]
        return local.rerank(query, chunks, top_k)

    def _get_local(self) -> CrossEncoderReranker | None:
        if self._local is not None:
            return self._local
        self._local = _load_reranker()
        return self._local


class CrossEncoderReranker:
    """Generic cross-encoder reranker supporting any HF sequence-classification model."""

    def __init__(self, model_path: str | Path, device: str = "cpu"):
        load_start = time.monotonic()
        self.tokenizer = AutoTokenizer.from_pretrained(
            str(model_path), trust_remote_code=True,
        )
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token_id = self.tokenizer.eos_token_id
        self.model = (
            AutoModelForSequenceClassification.from_pretrained(
                str(model_path), trust_remote_code=True,
            )
            .eval()
        )
        if self.model.config.pad_token_id is None:
            self.model.config.pad_token_id = self.tokenizer.pad_token_id
        self.device = device
        if device != "cpu":
            self.model = self.model.to(device)
        logger.info(
            "Loaded reranker model=%s path=%s device=%s elapsed=%.2fs",
            settings.reranker_model_id, model_path, device, time.monotonic() - load_start,
        )

    def rerank(self, query: str, chunks: list[Chunk], top_k: int) -> list[Chunk]:
        if not chunks:
            return []
        passages = [chunk.text for chunk in chunks]
        pairs = [[query, passage] for passage in passages]
        inputs = self.tokenizer(
            pairs, padding=True, truncation=True,
            max_length=settings.reranker_max_length, return_tensors="pt",
        )
        with torch.no_grad():
            logits = self.model(**inputs).logits
        # 兼容 num_labels=1（单分）和 num_labels>1（取末维正类分）
        if logits.shape[-1] == 1:
            scores = logits.squeeze(-1).tolist()
        else:
            scores = logits[:, -1].tolist()
        if isinstance(scores, float):
            scores = [scores]
        scored = list(zip(scores, chunks))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [chunk for _, chunk in scored[:top_k]]


def get_reranker() -> CrossEncoderReranker | FallbackReranker | None:
    if not settings.reranker_enabled:
        return None
    return FallbackReranker()


def _load_reranker() -> CrossEncoderReranker | None:
    model_path = _resolve_reranker_model_path()
    if model_path is None:
        return None
    try:
        return CrossEncoderReranker(model_path, device=settings.reranker_device)
    except Exception:
        logger.exception("Failed to load reranker model, reranker disabled")
        return None


def _reranker_model_dir() -> Path:
    from backend.domain.config import model_dir
    model_name = settings.reranker_model_id.rsplit("/", 1)[-1]
    return model_dir() / "reranker" / model_name


def _resolve_reranker_model_path() -> Path | None:
    model_path = _reranker_model_dir()
    if model_path.exists() and (model_path / "config.json").is_file():
        return model_path
    if settings.reranker_auto_download:
        try:
            model_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot_download(
                settings.reranker_model_id,
                cache_dir=str(model_path.parent),
                local_dir=str(model_path),
            )
            return model_path
        except Exception:
            logger.exception("Failed to download reranker model")
            return None
    return None
