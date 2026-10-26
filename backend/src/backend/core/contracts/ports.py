"""Ports: capabilities the use cases depend on, implemented by adapters.

Use cases are typed against these protocols so the concrete implementation
(DeepSeek, sentence-transformers, FAISS) is chosen once, in the composition
root, instead of every module importing a global singleton.
"""

from collections.abc import Iterator
from typing import Protocol, runtime_checkable


@runtime_checkable
class TextCompleter(Protocol):
    """Text completion capability (non-streaming and streaming)."""

    def complete(self, prompt: str) -> str: ...

    def stream(self, prompt: str) -> Iterator[str]: ...


@runtime_checkable
class Embedder(Protocol):
    """Batch text embedding: one vector per input string."""

    def __call__(self, texts: list[str]) -> list[list[float]]: ...
