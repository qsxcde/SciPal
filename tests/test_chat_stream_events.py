"""Chat streaming: event order and failure paths of the SSE use case."""

import pytest

pytest.importorskip("faiss", reason="faiss-cpu is not installed")
pytest.importorskip("torch", reason="torch is not installed")

from backend.application import chat as chat_module
from backend.domain.exceptions import ActiveIndexNotReadyError
from backend.storage.sqlite import messages as message_repo
from backend.storage.sqlite import sessions


async def _collect(events):
    return [event async for event in events]


def _stub(monkeypatch, stream_factory, *, resolve=None):
    async def _default_resolve(session_id, **_kwargs):
        return object(), None

    monkeypatch.setattr(chat_module, "resolve_session_store", resolve or _default_resolve)
    if stream_factory is not None:
        monkeypatch.setattr(chat_module.chat_pipeline, "stream_answer", stream_factory)


@pytest.fixture
def session():
    return sessions.create_session("chat stream")


@pytest.mark.integration
async def test_event_order_is_status_tokens_sources_done(monkeypatch, session):
    def _stream(_store, _content, *, options, policy, history):
        yield "Hel"
        yield "lo"
        yield {"type": "sources", "value": [{"section": "Intro", "chunk_index": 0}]}

    _stub(monkeypatch, _stream)

    events = await _collect(chat_module.stream_session_chat(session["id"], "question"))

    assert [type(event).__name__ for event in events] == [
        "StatusEvent",
        "StatusEvent",
        "TokenEvent",
        "TokenEvent",
        "SourcesEvent",
        "DoneEvent",
    ]
    assert [event.value for event in events[:2]] == ["retrieving", "generating"]
    assert events[2].value + events[3].value == "Hello"
    assert events[4].value[0].section == "Intro"

    stored = message_repo.list_messages(session["id"])
    assert [message["role"] for message in stored] == ["user", "assistant"]
    assert stored[-1]["content"] == "Hello"
    assert stored[-1]["status"] == "complete"


@pytest.mark.integration
async def test_explicit_protocol_without_sources_fails_the_turn(monkeypatch, session):
    def _stream(_store, _content, *, options, policy, history):
        yield {"type": "token", "value": "partial"}

    _stub(monkeypatch, _stream)

    events = await _collect(chat_module.stream_session_chat(session["id"], "question"))

    assert [type(event).__name__ for event in events] == [
        "StatusEvent",
        "StatusEvent",
        "TokenEvent",
        "ErrorEvent",
        "DoneEvent",
    ]

    stored = message_repo.list_messages(session["id"])
    assert stored[-1]["status"] == "failed"
    assert stored[-1]["content"] == "partial"


@pytest.mark.integration
async def test_index_not_ready_reports_a_failed_turn(monkeypatch, session):
    async def _resolve(session_id, **_kwargs):
        raise ActiveIndexNotReadyError("still indexing", session_id=session_id)

    _stub(monkeypatch, None, resolve=_resolve)

    events = await _collect(chat_module.stream_session_chat(session["id"], "question"))

    assert [type(event).__name__ for event in events] == [
        "TokenEvent",
        "SourcesEvent",
        "DoneEvent",
    ]
    assert events[1].value == []
    assert message_repo.list_messages(session["id"])[-1]["status"] == "failed"


@pytest.mark.integration
async def test_regenerate_replaces_the_previous_answer(monkeypatch, session):
    message_repo.create_message(session["id"], "user", "question")
    message_repo.create_message(session["id"], "assistant", "old answer")

    def _stream(_store, _content, *, options, policy, history):
        yield {"type": "token", "value": "new answer"}
        yield {"type": "sources", "value": []}

    _stub(monkeypatch, _stream)

    await _collect(
        chat_module.stream_session_chat(session["id"], "question", regenerate=True)
    )

    stored = message_repo.list_messages(session["id"])
    assert [message["role"] for message in stored] == ["user", "assistant"]
    assert stored[-1]["content"] == "new answer"

@pytest.mark.integration
async def test_client_abort_persists_a_stopped_answer(monkeypatch, session):
    def _stream(_store, _content, *, options, policy, history):
        yield {"type": "token", "value": "half"}
        yield {"type": "token", "value": " answer"}
        yield {"type": "sources", "value": []}

    _stub(monkeypatch, _stream)

    events = chat_module.stream_session_chat(session["id"], "question")
    await events.__anext__()  # retrieving
    await events.__anext__()  # generating
    token_event = await events.__anext__()
    assert token_event.value == "half"

    await events.aclose()

    stored = message_repo.list_messages(session["id"])
    assert stored[-1]["role"] == "assistant"
    assert stored[-1]["content"] == "half"
    assert stored[-1]["status"] == "stopped"
