"""重新生成：只删除紧随其后的旧回答，不影响其他消息。"""

import pytest

from backend.storage.sqlite import messages as message_repo
from backend.storage.sqlite import sessions as session_repo


def _seed() -> str:
    session = session_repo.create_session("重新生成测试")
    return session["id"]


@pytest.mark.integration
def test_deletes_trailing_assistant_answer():
    session_id = _seed()
    message_repo.create_message(session_id=session_id, role="user", content="问题")
    message_repo.create_message(session_id=session_id, role="assistant", content="旧回答")

    removed = message_repo.delete_trailing_assistant_message(session_id)

    remaining = message_repo.list_messages(session_id)
    assert removed is True
    assert [(item["role"], item["content"]) for item in remaining] == [("user", "问题")]


@pytest.mark.integration
def test_refuses_when_last_message_is_user():
    session_id = _seed()
    message_repo.create_message(session_id=session_id, role="user", content="问题")

    removed = message_repo.delete_trailing_assistant_message(session_id)

    assert removed is False
    assert len(message_repo.list_messages(session_id)) == 1


@pytest.mark.integration
def test_empty_session_is_a_noop():
    session_id = _seed()

    assert message_repo.delete_trailing_assistant_message(session_id) is False


@pytest.mark.integration
def test_only_the_last_answer_is_removed():
    session_id = _seed()
    message_repo.create_message(session_id=session_id, role="user", content="第一问")
    message_repo.create_message(session_id=session_id, role="assistant", content="第一答")
    message_repo.create_message(session_id=session_id, role="user", content="第二问")
    message_repo.create_message(session_id=session_id, role="assistant", content="第二答")

    assert message_repo.delete_trailing_assistant_message(session_id) is True
    assert [item["content"] for item in message_repo.list_messages(session_id)] == [
        "第一问",
        "第一答",
        "第二问",
    ]
