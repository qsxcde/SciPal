from enum import StrEnum
from typing import Final


class SessionStatus(StrEnum):
    empty = "empty"
    processing = "processing"
    ready = "ready"
    degraded = "degraded"
    failed = "failed"


class DocumentStage(StrEnum):
    uploaded = "uploaded"
    parsing = "parsing"
    parsed = "parsed"
    chunked = "chunked"
    indexing = "indexing"
    ready = "ready"
    failed = "failed"


class IndexSnapshotStatus(StrEnum):
    building = "building"
    ready = "ready"
    failed = "failed"
    stale = "stale"


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"
    interrupted = "interrupted"


TERMINAL_JOB_STATUSES: Final[frozenset[JobStatus]] = frozenset(
    {
        JobStatus.succeeded,
        JobStatus.failed,
        JobStatus.cancelled,
        JobStatus.interrupted,
    }
)
