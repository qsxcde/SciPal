"""Garbage-collect index snapshot files that can no longer serve retrieval.

Every successful ingestion leaves the previous ``ready`` snapshot behind as
``stale`` so that a failed promotion can roll back. Those files (and ``failed``
candidates) are never removed by the application, so they accumulate on disk.

This script removes

* every ``failed`` snapshot, and
* ``stale`` snapshots whose ``updated_at`` is older than ``--stale-days``.

``ready`` and ``building`` snapshots are never touched. Run it while no
ingestion is in progress (a rollback right after promotion relies on the
previous ``stale`` files).

Usage::

    uv run --project backend python -m backend.scripts.gc_index_snapshots
    uv run --project backend python -m backend.scripts.gc_index_snapshots --apply
"""

import argparse
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from backend.config import data_dir
from backend.storage.sqlite import index_snapshots as snapshot_repo
from backend.storage.sqlite.schema import init_db

logger = logging.getLogger(__name__)


def _stale_cutoff(stale_days: int) -> str:
    """Return a timestamp comparable with the ISO8601 strings stored in SQLite."""
    if stale_days < 0:
        raise ValueError("stale_days must be >= 0")
    return (datetime.now(UTC) - timedelta(days=stale_days)).isoformat()


def _is_inside_index_root(path: Path, index_root: Path) -> bool:
    try:
        return path.resolve().is_relative_to(index_root)
    except OSError:
        return False


def collect_snapshots(stale_days: int = 7, apply: bool = False) -> dict[str, int]:
    """Delete collectable snapshot files; returns a small summary for logging/tests."""
    index_root = (data_dir() / "index").resolve()
    snapshots = snapshot_repo.list_snapshots_pending_cleanup(_stale_cutoff(stale_days))

    summary = {
        "candidates": len(snapshots),
        "files_deleted": 0,
        "rows_deleted": 0,
        "skipped_paths": 0,
    }
    for snapshot in snapshots:
        for column in ("index_path", "chunks_path"):
            raw_path = snapshot.get(column)
            if not raw_path:
                continue
            path = Path(raw_path)
            if not _is_inside_index_root(path, index_root):
                logger.warning(
                    "Skip snapshot file outside data dir: snapshot_id=%s path=%s",
                    snapshot["id"],
                    path,
                )
                summary["skipped_paths"] += 1
                continue
            if not path.exists():
                continue
            if apply:
                path.unlink()
            summary["files_deleted"] += 1

        if apply and snapshot_repo.delete_snapshot(snapshot["id"]):
            summary["rows_deleted"] += 1

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove failed/stale index snapshot files that are no longer serving"
    )
    parser.add_argument(
        "--stale-days",
        type=int,
        default=7,
        help="keep stale snapshots newer than N days (default: 7)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually delete files and rows (default: dry run)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    init_db()
    summary = collect_snapshots(stale_days=args.stale_days, apply=args.apply)
    mode = "applied" if args.apply else "dry-run"
    print(
        f"[{mode}] candidates={summary['candidates']} "
        f"files={summary['files_deleted']} rows={summary['rows_deleted']} "
        f"skipped_paths={summary['skipped_paths']}"
    )


if __name__ == "__main__":
    main()
