"""Bounded reading of upload bodies.

``UploadFile.file.read()`` returns the whole body, so a client could exhaust
memory before the size limit is ever checked. Reading in chunks keeps the peak
at ``upload_max_bytes`` regardless of how much the client sends.
"""

from fastapi import UploadFile

from backend.config import settings
from backend.domain.exceptions import UploadTooLargeError

# Multipart framing adds headers and boundaries on top of the file itself.
MULTIPART_OVERHEAD_ALLOWANCE = 1024 * 1024
_CHUNK_SIZE = 1024 * 1024


def reject_by_content_length(content_length: str | None) -> None:
    """Fail fast on an obviously oversized body, before reading any of it."""
    if not content_length or not content_length.isdigit():
        return
    declared = int(content_length)
    limit = settings.upload_max_bytes + MULTIPART_OVERHEAD_ALLOWANCE
    if declared > limit:
        raise UploadTooLargeError(
            f"File too large (max {settings.upload_max_bytes} bytes)"
        )


def read_upload_with_limit(file: UploadFile, max_bytes: int | None = None) -> bytes:
    """Read the body in chunks and abort as soon as the limit is exceeded."""
    limit = settings.upload_max_bytes if max_bytes is None else max_bytes
    buffer = bytearray()
    while True:
        chunk = file.file.read(_CHUNK_SIZE)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > limit:
            raise UploadTooLargeError(f"File too large (max {limit} bytes)")
    return bytes(buffer)
