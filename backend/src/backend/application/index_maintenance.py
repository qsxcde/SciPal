"""Index refresh hooks used after a document changes."""

import logging

from backend.application.indexing import rebuild_session_snapshot
from backend.adapters.vector.store_cache import discard_store
from backend.storage.sqlite import index_snapshots as snapshot_repo
from backend.storage.sqlite import indexes as index_repo

logger = logging.getLogger(__name__)


def refresh_after_document_change(session_id: str) -> None:
    """Rebuild the session index after a document was removed."""
    rebuild_session_snapshot(session_id)


def invalidate_session_index(session_id: str, reason: str) -> None:
    """Mark the active index unusable so retrieval stops serving stale vectors."""
    snapshot = snapshot_repo.get_active_ready_snapshot(session_id)
    if snapshot is not None:
        snapshot_repo.mark_snapshot_failed(snapshot["id"], reason)
    index_repo.upsert_index(session_id, "", "", "failed")
    discard_store(session_id)
    logger.warning("Invalidated index for session=%s reason=%s", session_id, reason)
