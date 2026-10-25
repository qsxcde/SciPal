"""阅读器正文：从 IR 产物还原有序、可锚定的段落。"""

import json
from pathlib import Path

import pytest

from backend.application.documents import get_document_content
from backend.domain.exceptions import DocumentNotFoundError
from backend.storage.sqlite import documents as document_repo
from backend.storage.sqlite import sessions as session_repo


def _seed_document(ir_path: str | None) -> tuple[str, str]:
    session = session_repo.create_session("阅读器测试")
    document = document_repo.create_document(
        session_id=session["id"],
        filename="paper.pdf",
        file_path="/tmp/paper.pdf",
        mime_type="application/pdf",
        file_size=2048,
    )
    document_repo.update_document_artifacts(
        document_id=document["id"],
        parsed_ir_path=ir_path,
        parsed_markdown_path=None,
        quality_report_path=None,
        parser_name="mineru",
        parser_version="2.1",
        parse_quality_status="good",
    )
    return session["id"], document["id"]


def _write_ir(tmp_path: Path) -> Path:
    payload = {
        "document_id": "doc-1",
        "filename": "paper.pdf",
        "page_count": 2,
        "parser_name": "mineru",
        "parser_version": "2.1",
        "pages": [
            {
                "page_number": 2,
                "blocks": [
                    {
                        "id": "b-late",
                        "page_number": 2,
                        "block_index": 0,
                        "type": "paragraph",
                        "text": "第二页正文",
                        "reading_order": 1,
                        "section_path": ["4", "Experiment"],
                    }
                ],
            },
            {
                "page_number": 1,
                "blocks": [
                    {
                        "id": "b-head",
                        "page_number": 1,
                        "block_index": 2,
                        "type": "header_footer",
                        "text": "页眉",
                        "reading_order": 0,
                        "section_path": [],
                    },
                    {
                        "id": "b-title",
                        "page_number": 1,
                        "block_index": 0,
                        "type": "title",
                        "text": "论文标题",
                        "reading_order": 0,
                        "section_path": ["1"],
                    },
                    {
                        "id": "b-empty",
                        "page_number": 1,
                        "block_index": 1,
                        "type": "paragraph",
                        "text": "   ",
                        "reading_order": 2,
                        "section_path": ["1"],
                    },
                ],
            },
        ],
        "blocks": [],
        "outline": ["1", "4"],
        "quality_report": {
            "parser_name": "mineru",
            "parser_version": "2.1",
            "page_count": 2,
        },
    }
    path = tmp_path / "document.ir.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.mark.integration
def test_blocks_are_ordered_and_noise_is_filtered(tmp_path):
    ir_path = _write_ir(tmp_path)
    session_id, document_id = _seed_document(str(ir_path))

    content = get_document_content(session_id, document_id)

    assert [block["id"] for block in content["blocks"]] == ["b-title", "b-late"]
    assert content["blocks"][1]["section_path"] == ["4", "Experiment"]
    assert content["filename"] == "paper.pdf"
    assert content["parser_name"] == "mineru"
    assert content["chunk_count"] == 0


@pytest.mark.integration
def test_missing_ir_file_yields_empty_blocks(tmp_path):
    session_id, document_id = _seed_document(str(tmp_path / "missing.ir.json"))

    content = get_document_content(session_id, document_id)

    assert content["blocks"] == []


@pytest.mark.integration
def test_document_is_scoped_to_session(tmp_path):
    ir_path = _write_ir(tmp_path)
    _, document_id = _seed_document(str(ir_path))
    other_session = session_repo.create_session("另一个会话")

    with pytest.raises(DocumentNotFoundError):
        get_document_content(other_session["id"], document_id)
