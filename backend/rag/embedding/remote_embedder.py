"""Remote embedding via OpenAI-compatible API (Gitee AI / etc.)."""
import logging
import time

from openai import OpenAI

from backend.domain.config import settings
from backend.rag.embedding.local_embedder import truncate_for_embedding

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=settings.embedding_remote_base_url,
            api_key=settings.embedding_remote_api_key,
            timeout=30,
        )
    return _client


def embed(texts: list[str]) -> list[list[float]]:
    """Embed texts via remote API (OpenAI-compatible)."""
    client = _get_client()
    truncated = [truncate_for_embedding(t) for t in texts]

    start = time.monotonic()
    logger.info("Encoding %d texts with remote embedding model=%s", len(texts), settings.embedding_remote_model)

    resp = client.embeddings.create(
        model=settings.embedding_remote_model,
        input=truncated,
    )

    sorted_data = sorted(resp.data, key=lambda x: x.index)
    rows = [d.embedding for d in sorted_data]
    dimension = len(rows[0]) if rows else 0
    logger.info(
        "Encoded %d texts via remote API dimension=%d elapsed=%.2fs",
        len(rows), dimension, time.monotonic() - start,
    )
    return rows
