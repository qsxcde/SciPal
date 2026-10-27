"""Ports: capabilities the use cases depend on, implemented by adapters.

Use cases are typed against these protocols so the concrete implementation
(DeepSeek, sentence-transformers, FAISS) is chosen once, in the composition
root, instead of every module importing a global singleton.
"""

from collections.abc import Callable, Iterator
from typing import Protocol, runtime_checkable

from backend.domain.models import Chunk


@runtime_checkable
class TextCompleter(Protocol):
    """Text completion capability (non-streaming and streaming)."""

    def complete(self, prompt: str) -> str: ...

    def stream(self, prompt: str) -> Iterator[str]: ...


# Batch text embedding: one vector per input string.
Embedder = Callable[[list[str]], list[list[float]]]


@runtime_checkable
class VectorStore(Protocol):
    """Read/write surface the retrieval and indexing code depends on."""

    def add_chunks(self, chunks: list[Chunk]) -> None: ...

    def search(self, query: str, k: int = 5) -> list[Chunk]: ...

    def list_chunks(self) -> list[Chunk]: ...
