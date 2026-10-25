"""文献库列表：跨会话聚合，并按会话归属与归档状态过滤。"""

import pytest

from backend.application.documents import list_library_documents
from backend.storage.sqlite import documents as document_repo
from backend.storage.sqlite import sessions as session_repo


def _seed_document(session_id: str, filename: str) -> None:
    document_repo.create_document(
        session_id=session_id,
        filename=filename,
        file_path=f"/tmp/{filename}",
        mime_type="application/pdf",
        file_size=1024,
    )


def _seed_sessions() -> dict[str, str]:
    mine = session_repo.create_session("我的论文", user_id="u1")
    other = session_repo.create_session("别人的论文", user_id="u2")
    legacy = session_repo.create_session("历史会话")
    archived = session_repo.create_session("已归档", user_id="u1")

    _seed_document(mine["id"], "mine.pdf")
    _seed_document(other["id"], "other.pdf")
    _seed_document(legacy["id"], "legacy.pdf")
    _seed_document(archived["id"], "archived.pdf")

    session_repo.archive_session(archived["id"])
    return {"mine": mine["id"], "legacy": legacy["id"]}


@pytest.mark.integration
def test_lists_own_and_legacy_documents_only():
    _seed_sessions()

    filenames = {item["filename"] for item in list_library_documents("u1")}

    assert filenames == {"mine.pdf", "legacy.pdf"}


@pytest.mark.integration
def test_anonymous_scope_only_sees_legacy_documents():
    _seed_sessions()

    filenames = {item["filename"] for item in list_library_documents(None)}

    assert filenames == {"legacy.pdf"}


@pytest.mark.integration
def test_items_carry_session_context():
    ids = _seed_sessions()

    items = {item["filename"]: item for item in list_library_documents("u1")}
    mine = items["mine.pdf"]

    assert mine["session_id"] == ids["mine"]
    assert mine["session_title"] == "我的论文"
    assert mine["chunk_count"] == 0
    assert mine["status"] == "uploaded"
