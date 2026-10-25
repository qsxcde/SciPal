"""索引元数据写入：首次插入也要补齐 created_at。"""

import pytest

from backend.storage.sqlite import indexes as index_repo
from backend.storage.sqlite import sessions as session_repo


@pytest.mark.integration
def test_upsert_inserts_created_at_on_first_write():
    session = session_repo.create_session("索引元数据")

    row = index_repo.upsert_index(session["id"], "/tmp/a.index", "/tmp/a.json", "ready")

    assert row["session_id"] == session["id"]
    assert row["status"] == "ready"
    assert row["created_at"]


@pytest.mark.integration
def test_upsert_updates_existing_row_without_touching_created_at():
    session = session_repo.create_session("索引元数据")
    created = index_repo.upsert_index(session["id"], "/tmp/a.index", "/tmp/a.json", "ready")

    updated = index_repo.upsert_index(session["id"], "", "", "failed")

    assert updated["status"] == "failed"
    assert updated["created_at"] == created["created_at"]
