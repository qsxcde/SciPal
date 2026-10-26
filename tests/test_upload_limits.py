"""Bounded upload reading: the size limit must hold while the body is read."""

import io

import pytest

from backend.api import uploads
from backend.domain.exceptions import UploadTooLargeError


class _FakeUpload:
    """Minimal stand-in for fastapi.UploadFile."""

    def __init__(self, payload: bytes) -> None:
        self.file = io.BytesIO(payload)

    @property
    def consumed(self) -> int:
        return self.file.tell()


@pytest.mark.unit
def test_streaming_read_returns_the_whole_body_under_the_limit():
    upload = _FakeUpload(b"%PDF-1.7 payload")

    assert uploads.read_upload_with_limit(upload, max_bytes=1024) == b"%PDF-1.7 payload"


@pytest.mark.unit
def test_streaming_read_aborts_once_the_limit_is_exceeded(monkeypatch):
    monkeypatch.setattr(uploads, "_CHUNK_SIZE", 4)
    upload = _FakeUpload(b"x" * 100)

    with pytest.raises(UploadTooLargeError):
        uploads.read_upload_with_limit(upload, max_bytes=10)

    # Only one chunk past the limit is read; the rest of the body never is.
    assert upload.consumed <= 14


@pytest.mark.unit
def test_content_length_is_rejected_before_reading_any_body(monkeypatch):
    monkeypatch.setattr(uploads.settings, "upload_max_bytes", 1024)

    with pytest.raises(UploadTooLargeError):
        uploads.reject_by_content_length(str(2 * 1024 * 1024))

    assert uploads.reject_by_content_length(str(1024)) is None
    assert uploads.reject_by_content_length(None) is None
