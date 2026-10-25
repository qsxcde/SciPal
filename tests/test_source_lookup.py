"""引用定位：把回答里的 source 还原成完整段落。"""

import pytest

from backend.application.documents import get_source_chunk
from backend.domain.exceptions import ChunkNotFoundError
from backend.domain.models import Chunk, ChunkMetadata
from backend.storage.sqlite import chunks as chunk_repo
from backend.storage.sqlite import documents as document_repo
from backend.storage.sqlite import sessions as session_repo

LONG_TEXT = "这是被引用的完整段落。" * 40


def _seed_chunk() -> tuple[str, str]:
    session = session_repo.create_session("引用测试")
    document = document_repo.create_document(
        session_id=session["id"],
        filename="paper.pdf",
        file_path="/tmp/paper.pdf",
        mime_type="application/pdf",
        file_size=1024,
    )
    chunk_repo.insert_chunks(
        session["id"],
        document["id"],
        [
            Chunk(
                text=LONG_TEXT,
                metadata=ChunkMetadata(
                    paper_id=document["id"],
                    section="3 > Method",
                    chunk_index=0,
                    type="paragraph",
                    section_path=["3", "Method"],
                    page_start=4,
                    page_end=5,
                    block_ids=["b-1", "b-2"],
                ),
            )
        ],
    )
    return session["id"], document["id"]


@pytest.mark.integration
def test_returns_full_chunk_text_not_excerpt():
    session_id, document_id = _seed_chunk()

    result = get_source_chunk(session_id, document_id, 0)

    assert result["text"] == LONG_TEXT
    assert len(result["text"]) > 240
    assert result["section"] == "3 > Method"
    assert result["section_path"] == ["3", "Method"]
    assert result["page_start"] == 4
    assert result["page_end"] == 5
    assert result["block_ids"] == ["b-1", "b-2"]


@pytest.mark.integration
def test_missing_chunk_raises_domain_error():
    session_id, document_id = _seed_chunk()

    with pytest.raises(ChunkNotFoundError):
        get_source_chunk(session_id, document_id, 99)


@pytest.mark.integration
def test_chunk_is_scoped_to_session():
    session_id, document_id = _seed_chunk()
    other_session = session_repo.create_session("另一个会话")

    with pytest.raises(ChunkNotFoundError):
        get_source_chunk(other_session["id"], document_id, 0)
