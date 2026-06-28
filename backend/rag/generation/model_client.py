"""Multi-provider LLM client with automatic fallback.

Supports any OpenAI-compatible API provider. Providers are tried in priority
order — if one fails, the next is attempted automatically.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Generator
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from backend.domain.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ProviderConfig:
    """Configuration for a single LLM provider."""

    name: str
    base_url: str
    api_key: str | None
    model: str
    priority: int = 10
    timeout: float = 60.0


def build_providers() -> list[ProviderConfig]:
    """Build provider list from settings, sorted by priority.

    Primary: DeepSeek (always present, key required at startup).
    Fallback 1: OpenAI-compatible API (GLM / Qwen / SiliconFlow), optional.
    Fallback 2: Local Ollama endpoint, optional.
    """
    providers: list[ProviderConfig] = []

    providers.append(
        ProviderConfig(
            name="deepseek",
            base_url=settings.deepseek_base_url,
            api_key=settings.deepseek_api_key,
            model=settings.deepseek_model,
            priority=1,
        )
    )

    if settings.llm_fallback_enabled and settings.fallback_base_url:
        providers.append(
            ProviderConfig(
                name="fallback",
                base_url=settings.fallback_base_url,
                api_key=settings.fallback_api_key,
                model=settings.fallback_model,
                priority=10,
            )
        )

    if settings.llm_fallback_enabled and settings.ollama_base_url:
        providers.append(
            ProviderConfig(
                name="ollama",
                base_url=settings.ollama_base_url,
                api_key=None,
                model=settings.ollama_model,
                priority=20,
            )
        )

    return providers


class ModelClient:
    """Multi-provider LLM client with automatic sequential fallback.

    Usage:
        client = ModelClient()
        client.complete("What is RAG?")
        for token in client.stream("Explain transformers"):
            ...
    """

    def __init__(self, providers: list[ProviderConfig] | None = None) -> None:
        self._providers = sorted(
            providers if providers is not None else build_providers(),
            key=lambda p: p.priority,
        )
        self._clients: dict[str, OpenAI] = {}
        self._last_success: dict[str, float] = {}

    @property
    def provider_count(self) -> int:
        return len(self._providers)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def complete(
        self,
        prompt: str,
        messages: list[dict[str, Any]] | None = None,
    ) -> str:
        """Try each provider in priority order. Returns the first successful response."""
        if not self._providers:
            raise RuntimeError("No LLM providers configured")

        errors: list[str] = []
        for provider in self._providers:
            try:
                client = self._get_or_create_client(provider)
                msgs = messages if messages is not None else [
                    {"role": "user", "content": prompt},
                ]
                response = client.chat.completions.create(
                    model=provider.model,
                    messages=msgs,
                    stream=False,
                    temperature=0,
                )
                if not response.choices:
                    raise RuntimeError(
                        f"Provider {provider.name}: response contained no choices"
                    )
                content = response.choices[0].message.content
                if content is None:
                    raise RuntimeError(
                        f"Provider {provider.name}: response content was empty"
                    )
                self._record_success(provider.name)
                return str(content)
            except Exception as e:
                errors.append(f"{provider.name}: {e!s}")
                logger.warning(
                    "LLM provider %s failed (complete), falling back: %s",
                    provider.name,
                    e,
                )

        raise RuntimeError(
            f"All {len(self._providers)} LLM providers failed: {'; '.join(errors)}"
        )

    def stream(
        self,
        prompt: str,
        messages: list[dict[str, Any]] | None = None,
    ) -> Generator[str, None, None]:
        """Stream tokens from the first successful provider."""
        if not self._providers:
            raise RuntimeError("No LLM providers configured")

        errors: list[str] = []
        for provider in self._providers:
            try:
                client = self._get_or_create_client(provider)
                msgs = messages if messages is not None else [
                    {"role": "user", "content": prompt},
                ]
                response = client.chat.completions.create(
                    model=provider.model,
                    messages=msgs,
                    stream=True,
                )
                for chunk in response:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        yield delta
                self._record_success(provider.name)
                return
            except Exception as e:
                errors.append(f"{provider.name}: {e!s}")
                logger.warning(
                    "LLM stream from %s failed, falling back: %s",
                    provider.name,
                    e,
                )

        raise RuntimeError(
            f"All {len(self._providers)} LLM providers failed for streaming: "
            f"{'; '.join(errors)}"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_or_create_client(self, provider: ProviderConfig) -> OpenAI:
        cache_key = f"{provider.base_url}|{provider.api_key}"
        if cache_key not in self._clients:
            self._clients[cache_key] = OpenAI(
                api_key=provider.api_key,
                base_url=provider.base_url,
                timeout=provider.timeout,
            )
        return self._clients[cache_key]

    def _record_success(self, name: str) -> None:
        self._last_success[name] = time.monotonic()
