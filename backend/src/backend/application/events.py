"""Streaming events emitted by application use cases.

These are transport-agnostic: the HTTP layer (``backend.api.streaming``) is
responsible for turning them into SSE frames.
"""

from dataclasses import dataclass

from backend.domain.models import SourceRef


@dataclass(frozen=True, slots=True)
class StatusEvent:
    value: str


@dataclass(frozen=True, slots=True)
class TokenEvent:
    value: str


@dataclass(frozen=True, slots=True)
class SourcesEvent:
    value: list[SourceRef]


@dataclass(frozen=True, slots=True)
class WarningEvent:
    value: str


@dataclass(frozen=True, slots=True)
class ErrorEvent:
    value: str


@dataclass(frozen=True, slots=True)
class DoneEvent:
    pass


ChatEvent = StatusEvent | TokenEvent | SourcesEvent | WarningEvent | ErrorEvent | DoneEvent
