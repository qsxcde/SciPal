"""Composition root: capability objects must satisfy their ports."""

import pytest

from backend.composition import text_completer
from backend.core.contracts.ports import TextCompleter


@pytest.mark.unit
def test_text_completer_satisfies_the_port():
    completer = text_completer()

    assert isinstance(completer, TextCompleter)


@pytest.mark.unit
def test_text_completer_is_created_once():
    assert text_completer() is text_completer()


@pytest.mark.unit
def test_embedder_factory_returns_a_callable(monkeypatch):
    pytest.importorskip("torch", reason="the embedder loads sentence-transformers")
    from backend.composition import embedder

    assert callable(embedder())


@pytest.mark.unit
def test_faiss_store_satisfies_the_vector_store_port():
    pytest.importorskip("faiss", reason="faiss-cpu is not installed")
    pytest.importorskip("torch", reason="the embedder import pulls torch")
    from backend.core.contracts.ports import VectorStore
    from backend.rag.indexing.vector_store import FAISSVectorStore

    assert isinstance(FAISSVectorStore(), VectorStore)
