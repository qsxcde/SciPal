"""LazyResource must build each client once, even under concurrent access."""

import threading

import pytest

from backend.rag.resources import LazyResource


@pytest.mark.unit
def test_builds_only_once():
    calls: list[int] = []

    def factory() -> object:
        calls.append(1)
        return object()

    resource: LazyResource[object] = LazyResource(factory)
    first = resource.get()
    second = resource.get()

    assert first is second
    assert len(calls) == 1


@pytest.mark.unit
def test_concurrent_access_builds_only_once():
    calls: list[int] = []
    barrier = threading.Barrier(8)

    def factory() -> object:
        calls.append(1)
        return object()

    resource: LazyResource[object] = LazyResource(factory)
    results: list[object] = []
    lock = threading.Lock()

    def worker() -> None:
        barrier.wait()
        value = resource.get()
        with lock:
            results.append(value)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(calls) == 1
    assert len({id(value) for value in results}) == 1
