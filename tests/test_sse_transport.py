"""SSE framing: domain events to wire frames."""

import json

import pytest

import asyncio

from backend.api.streaming import (
    HEARTBEAT_FRAME,
    encode_sse_event,
    stream_with_heartbeat,
    to_transport_event,
)
from backend.application.events import (
    DoneEvent,
    ErrorEvent,
    SourcesEvent,
    StatusEvent,
    TokenEvent,
    WarningEvent,
)
from backend.domain.models import SourceRef


@pytest.mark.unit
@pytest.mark.parametrize(
    ("event", "expected_type"),
    [
        (StatusEvent(value="retrieving"), "status"),
        (TokenEvent(value="hi"), "token"),
        (SourcesEvent(value=[]), "sources"),
        (WarningEvent(value="careful"), "warning"),
        (ErrorEvent(value="boom"), "error"),
        (DoneEvent(), "done"),
    ],
)
def test_every_domain_event_maps_to_one_wire_type(event, expected_type):
    transport = to_transport_event(event)

    assert transport.type == expected_type


@pytest.mark.unit
def test_unknown_domain_event_fails_loudly():
    with pytest.raises(TypeError):
        to_transport_event(object())  # type: ignore[arg-type]


@pytest.mark.unit
def test_frame_is_valid_json_with_the_sse_data_prefix():
    frame = encode_sse_event(
        SourcesEvent(
            value=[SourceRef(section="Intro", chunk_index=2, text_excerpt="quote")]
        )
    )

    assert frame.startswith("data: " )
    assert frame.endswith("\n\n")
    payload = json.loads(frame[len("data: "):].strip())
    assert payload["type"] == "sources"
    assert payload["value"][0]["section"] == "Intro"


@pytest.mark.unit
async def test_heartbeat_is_emitted_while_the_stream_stalls():
    gate = asyncio.Event()

    async def _slow_events():
        yield TokenEvent(value="first")
        await gate.wait()
        yield DoneEvent()

    frames = stream_with_heartbeat(_slow_events(), interval=0.01)

    first = await frames.__anext__()
    heartbeat = await frames.__anext__()

    gate.set()
    await frames.aclose()

    assert first.startswith("data: ")
    assert heartbeat == HEARTBEAT_FRAME


@pytest.mark.unit
async def test_heartbeat_stream_forwards_errors():
    async def _failing_events():
        raise RuntimeError("upstream broke")
        yield DoneEvent()  # pragma: no cover - unreachable

    frames = stream_with_heartbeat(_failing_events(), interval=0.01)

    with pytest.raises(RuntimeError, match="upstream broke"):
        await frames.__anext__()
