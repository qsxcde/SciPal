"""Remote reranker via SiliconFlow / OpenAI-compatible rerank API."""
import logging
import threading
import time

import httpx

from backend.domain.config import settings
from backend.rag.ingestion.metadata import Chunk

logger = logging.getLogger(__name__)

_client: httpx.Client | None = None
_client_lock = threading.Lock()


def _get_client() -> httpx.Client:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = httpx.Client(
                    base_url=settings.reranker_remote_base_url,
                    headers={
                        "Authorization": f"Bearer {settings.embedding_remote_api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=30,
                )
    return _client


def rerank(query: str, chunks: list[Chunk], top_k: int) -> list[Chunk] | None:
    """Rerank chunks via SiliconFlow rerank API. Returns None on failure."""
    if not chunks or not settings.embedding_remote_api_key:
        return None

    client = _get_client()
    documents = [c.text for c in chunks]

    start = time.monotonic()
    logger.info(
        "Reranking %d chunks via remote API model=%s",
        len(documents), settings.reranker_remote_model,
    )

    try:
        resp = client.post(
            "/rerank",
            json={
                "model": settings.reranker_remote_model,
                "query": query,
                "documents": documents,
                "top_n": top_k,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        indices = [r["index"] for r in results]
        reranked = [chunks[i] for i in indices if i < len(chunks)]
        logger.info(
            "Reranked %d chunks via remote API elapsed=%.2fs",
            len(reranked), time.monotonic() - start,
        )
        return reranked
    except Exception:
        logger.warning("Remote reranker failed", exc_info=True)
        return None
