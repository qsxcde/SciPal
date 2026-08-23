"""LLM client wrapper — delegates to ModelClient for multi-provider fallback.

Public API (unchanged):
    complete_text(prompt) -> str
    stream_completion_tokens(prompt) -> Generator[str]
"""
from __future__ import annotations

import logging
from collections.abc import Generator

from backend.domain.config import require_generation_settings
from backend.rag.generation.model_client import ModelClient, build_providers

logger = logging.getLogger(__name__)
_client: ModelClient | None = None


def _get_client() -> ModelClient:
    global _client
    if _client is None:
        require_generation_settings()
        _client = ModelClient(build_providers())
        logger.info(
            "Initialized ModelClient with %d provider(s)",
            _client.provider_count,
        )
    return _client


def complete_text(prompt: str) -> str:
    """Synchronous LLM completion. Delegates to ModelClient with fallback."""
    return _get_client().complete(prompt)


def stream_completion_tokens(prompt: str) -> Generator[str, None, None]:
    """Streaming LLM completion. Delegates to ModelClient with fallback."""
    return _get_client().stream(prompt)
