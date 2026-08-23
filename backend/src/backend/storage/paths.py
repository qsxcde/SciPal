"""Safe paths for session artifacts in the target SciPal data layout."""

import shutil
from pathlib import Path

from backend.domain.config import data_dir



def raw_session_dir(session_id: str) -> Path:
    path = data_dir() / "raw" / session_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def remove_session_dir(session_id: str) -> None:
    for root_name in ("raw", "parsed", "chunks", "index"):
        root = (data_dir() / root_name).resolve()
        target = (root / session_id).resolve()
        if not target.is_relative_to(root):
            raise ValueError("Session storage path is outside data directory")
        shutil.rmtree(target, ignore_errors=True)


def session_documents_dir(session_id: str) -> Path:
    return raw_session_dir(session_id)


def session_document_file_path(
    session_id: str,
    document_id: str,
    suffix: str = ".pdf",
) -> Path:
    return session_documents_dir(session_id) / f"{document_id}{suffix}"


def session_indexes_dir(session_id: str) -> Path:
    path = data_dir() / "index" / session_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def session_parsed_document_dir(session_id: str, document_id: str) -> Path:
    path = data_dir() / "parsed" / session_id / document_id
    path.mkdir(parents=True, exist_ok=True)
    return path
