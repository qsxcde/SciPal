"""SSE framing: domain events to wire frames."""

import json

import pytest

from backend.api.streaming import encode_sse_event, to_transport_event
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
