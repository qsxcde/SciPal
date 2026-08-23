"""Migrate legacy session artifacts into the target data layout."""

import argparse
import filecmp
import shutil
from pathlib import Path


def migrate_storage(
    source_data_dir: Path,
    target_data_dir: Path,
) -> None:
    """Move legacy session artifacts without overwriting conflicts."""
    sessions_dir = source_data_dir / "uploads" / "sessions"
    if sessions_dir.exists():
        for session_dir in sessions_dir.iterdir():
            if not session_dir.is_dir():
                continue
            _move_tree(
                session_dir / "documents",
                target_data_dir / "raw" / session_dir.name,
            )
            _move_tree(
                session_dir / "parsed",
                target_data_dir / "parsed" / session_dir.name,
            )
            _move_tree(
                session_dir / "indexes",
                target_data_dir / "index" / session_dir.name,
            )


def _move_tree(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    for path in source.rglob("*"):
        relative_path = path.relative_to(source)
        target = destination / relative_path
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if not filecmp.cmp(path, target, shallow=False):
                raise RuntimeError(f"Storage migration conflict: {target}")
            path.unlink()
            continue
        shutil.move(str(path), target)
    shutil.rmtree(source, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate legacy SciPal session storage")
    parser.add_argument("--source-data-dir", type=Path, default=Path("data"))
    parser.add_argument("--target-data-dir", type=Path, default=Path("backend/data"))
    args = parser.parse_args()
    migrate_storage(
        args.source_data_dir,
        args.target_data_dir,
    )


if __name__ == "__main__":
    main()
