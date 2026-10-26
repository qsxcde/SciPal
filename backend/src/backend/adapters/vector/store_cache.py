from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING

from backend.domain.states import PROCESSING_DOCUMENT_STAGES
from backend.rag.retrieval.filters import filter_indexable_chunks

if TYPE_CHECKING:
    from backend.rag.indexing.vector_store import FAISSVectorStore
from backend.storage.paths import session_indexes_dir
from backend.storage.sqlite import chunks as chunk_repo
from backend.storage.sqlite import documents as document_repo
from backend.storage.sqlite import index_snapshots as snapshot_repo
from backend.storage.sqlite import indexes as index_repo

_MAX_CACHED_STORES = 16
_stores: OrderedDict[str, tuple[str, FAISSVectorStore]] = OrderedDict()
_store_lock = threading.RLock()


def _cache_store(session_id: str, cache_key: str, store: FAISSVectorStore) -> None:
    """Insert into LRU cache, evicting oldest when at capacity."""
    _stores[session_id] = (cache_key, store)
    _stores.move_to_end(session_id)
    while len(_stores) > _MAX_CACHED_STORES:
        _stores.popitem(last=False)


def index_paths(session_id: str) -> tuple[str, str]:
    indexes_dir = session_indexes_dir(session_id)
    return str(indexes_dir / "faiss.index"), str(indexes_dir / "chunks.json")


def _new_store() -> FAISSVectorStore:
    """Import FAISS lazily so importing this module stays dependency-light."""
    from backend.rag.indexing.vector_store import FAISSVectorStore

    return FAISSVectorStore()


def _load_store(index_path: Path, chunks_path: Path) -> FAISSVectorStore:
    from backend.rag.indexing.vector_store import FAISSVectorStore

    return FAISSVectorStore.load(index_path=index_path, chunks_path=chunks_path)


def get_store(session_id: str) -> FAISSVectorStore:
    with _store_lock:
        metadata = index_repo.get_index(session_id)
        if metadata and metadata["status"] == "ready":
            cache_key = f"legacy:{metadata['updated_at']}"
            cached = _stores.get(session_id)
            if cached and cached[0] == cache_key:
                return cached[1]
            store = _load_store(
                Path(metadata["index_path"]),
                Path(metadata["chunks_path"]),
            )
            _cache_store(session_id, cache_key, store)
            return store

        ready_snapshot = snapshot_repo.get_active_ready_snapshot(session_id)
        if ready_snapshot is not None:
            return get_store_for_snapshot(ready_snapshot)

        existing_chunks = chunk_repo.list_chunks(session_id)
        session_documents = document_repo.list_documents(session_id)
        has_processing_documents = any(
            document["status"] in PROCESSING_DOCUMENT_STAGES
            for document in session_documents
        )
        if existing_chunks and not has_processing_documents:
            store = _new_store()
            store.add_chunks(filter_indexable_chunks(existing_chunks))
            return store

        store = _new_store()
        _cache_store(session_id, "empty", store)
        return store


def discard_store(session_id: str) -> None:
    with _store_lock:
        _stores.pop(session_id, None)


def get_store_for_snapshot(snapshot: dict) -> FAISSVectorStore:
    session_id = snapshot["session_id"]
    cache_key = f"snapshot:{snapshot['id']}:{snapshot['updated_at']}"
    with _store_lock:
        cached = _stores.get(session_id)
        if cached and cached[0] == cache_key:
            return cached[1]
        store = _load_store(
            Path(snapshot["index_path"]),
            Path(snapshot["chunks_path"]),
        )
        _cache_store(session_id, cache_key, store)
        return store
