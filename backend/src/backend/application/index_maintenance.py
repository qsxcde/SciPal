"""Index refresh hooks that stay importable without torch / faiss.

The real rebuild lives in ``application.indexing`` (which imports FAISS), so it
is resolved lazily here. Tests can monkeypatch this module without pulling in
the heavy dependencies.
"""

import logging

from backend.storage.sqlite import index_snapshots as snapshot_repo
from backend.storage.sqlite import indexes as index_repo

logger = logging.getLogger(__name__)


def refresh_after_document_change(session_id: str) -> None:
    """Rebuild the session index after a document was removed."""
    from backend.application.indexing import rebuild_session_snapshot

    rebuild_session_snapshot(session_id)


def invalidate_session_index(session_id: str, reason: str) -> None:
    """Mark the active index unusable so retrieval stops serving stale vectors."""
    from backend.application.store_cache import discard_store

    snapshot = snapshot_repo.get_active_ready_snapshot(session_id)
    if snapshot is not None:
        snapshot_repo.mark_snapshot_failed(snapshot["id"], reason)
    index_repo.upsert_index(session_id, "", "", "failed")
    discard_store(session_id)
    logger.warning("Invalidated index for session=%s reason=%s", session_id, reason)
