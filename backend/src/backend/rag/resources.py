"""Thread-safe lazy singletons for expensive external clients."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Generic, TypeVar

T = TypeVar("T")


class LazyResource(Generic[T]):
    """Build a resource on first use, exactly once, across threads."""

    def __init__(self, factory: Callable[[], T]) -> None:
        self._factory = factory
        self._lock = threading.Lock()
        self._value: T | None = None

    def get(self) -> T:
        value = self._value
        if value is not None:
            return value
        with self._lock:
            if self._value is None:
                self._value = self._factory()
            return self._value
