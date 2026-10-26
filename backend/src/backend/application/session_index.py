"""Resolve the active retrieval index of a session, waiting for it if needed."""

import asyncio
import time
from collections.abc import Callable

from backend.adapters.vector import store_cache
from backend.config import settings
from backend.domain.exceptions import ActiveIndexNotReadyError, SessionNotFoundError
from backend.storage.sqlite import index_snapshots as snapshot_repo
from backend.storage.sqlite import sessions as session_repo


async def resolve_session_store(
    session_id: str,
    wait_timeout_seconds: float | None = None,
    on_wait_for_index: Callable[[], None] | None = None,
) -> tuple[object, bool]:
    if wait_timeout_seconds is None:
        wait_timeout_seconds = settings.index_max_wait

    session = await asyncio.to_thread(session_repo.get_session, session_id)
    if session is None or session["is_archived"]:
        raise SessionNotFoundError(f"Session not found: {session_id}", session_id=session_id)

    ready_snapshot = await asyncio.to_thread(snapshot_repo.get_active_ready_snapshot, session_id)
    waited_for_index = False
    if ready_snapshot is None:
        waited_for_index = True
        if on_wait_for_index is not None:
            on_wait_for_index()
        ready_snapshot = await wait_for_ready_index(
            session_id,
            timeout_seconds=wait_timeout_seconds,
        )

    return store_cache.get_store_for_snapshot(ready_snapshot), waited_for_index


async def wait_for_ready_index(session_id: str, timeout_seconds: float) -> dict | None:
    deadline = time.monotonic() + timeout_seconds
    backoff = settings.index_poll_interval
    while time.monotonic() < deadline:
        ready_snapshot = await asyncio.to_thread(
            snapshot_repo.get_active_ready_snapshot, session_id
        )
        if ready_snapshot is not None:
            return ready_snapshot
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, settings.index_poll_max_interval)
    raise ActiveIndexNotReadyError(settings.msg_index_not_ready, session_id=session_id)
