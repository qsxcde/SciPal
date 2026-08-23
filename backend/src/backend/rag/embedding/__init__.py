"""Embedding module — provides a fallback chain: remote API → local embed.

Usage:

    from backend.rag.embedding import create_embed_fn

    embed_fn = create_embed_fn()
    vectors = embed_fn(["text1", "text2"])
"""
import logging
from typing import Callable

from backend.domain.config import settings
from backend.rag.embedding import local_embedder
from backend.rag.embedding import remote_embedder

logger = logging.getLogger(__name__)


def create_embed_fn() -> Callable[[list[str]], list[list[float]]]:
    """Build the embedding fallback chain.

    When ``embedding_remote_api_key`` is configured:
        remote_embed → local_embed

    Otherwise:
        local_embed (current default behavior)
    """
    fns: list[tuple[str, Callable[[list[str]], list[list[float]]]]] = [
        ("local", local_embedder.embed),
    ]
    if settings.embedding_remote_api_key:
        fns.insert(0, ("remote", remote_embedder.embed))
        logger.info("Embedding chain: remote -> local")
    else:
        logger.info("Embedding chain: local only")

    def _fallback_embed(texts: list[str]) -> list[list[float]]:
        first_error: Exception | None = None
        for name, fn in fns:
            try:
                return fn(texts)
            except Exception as exc:
                logger.warning("Embedder '%s' failed: %s", name, exc)
                if first_error is None:
                    first_error = exc
                continue
        raise RuntimeError("All embedders failed") from first_error

    return _fallback_embed
