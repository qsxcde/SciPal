import logging
import threading
import time
from pathlib import Path

import torch
from modelscope import snapshot_download
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from backend.domain.config import settings
from backend.rag.ingestion.metadata import Chunk

logger = logging.getLogger(__name__)

_reranker: "QwenReranker | None" = None
_reranker_lock = threading.Lock()


class QwenReranker:
    """Cross-encoder reranker using Qwen3-Reranker-0.6B."""

    def __init__(self, model_path: str | Path, device: str = "cpu"):
        load_start = time.monotonic()
        self.tokenizer = AutoTokenizer.from_pretrained(
            str(model_path), trust_remote_code=True,
        )
        # Qwen3-Reranker 无默认 pad_token，batch 推理需要
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
            "Loaded reranker model path=%s device=%s elapsed=%.2fs",
            model_path, device, time.monotonic() - load_start,
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
            scores = self.model(**inputs).logits.squeeze(-1).tolist()
        if isinstance(scores, float):
            scores = [scores]
        scored = list(zip(scores, chunks))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [chunk for _, chunk in scored[:top_k]]


def get_reranker() -> QwenReranker | None:
    """Lazy singleton — returns None if reranker is disabled or fails to load."""
    global _reranker
    if not settings.reranker_enabled:
        return None
    if _reranker is not None:
        return _reranker
    with _reranker_lock:
        if _reranker is not None:
            return _reranker
        _reranker = _load_reranker()
    return _reranker


def _load_reranker() -> QwenReranker | None:
    model_path = _resolve_reranker_model_path()
    if model_path is None:
        return None
    try:
        return QwenReranker(model_path, device=settings.reranker_device)
    except Exception:
        logger.exception("Failed to load reranker model, reranker disabled")
        return None


def _reranker_model_dir() -> Path:
    from backend.domain.config import model_dir
    return model_dir() / "reranker" / "Qwen3-Reranker-0.6B"


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
