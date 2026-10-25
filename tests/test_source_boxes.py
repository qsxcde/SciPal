"""引用块坐标：IR 里的 PDF 点坐标应归一化为 0-1，供原页高亮。"""

import json
from pathlib import Path

import pytest

from backend.application.documents import get_document_file, get_source_chunk
from backend.domain.exceptions import DocumentNotFoundError
from backend.domain.models import Chunk, ChunkMetadata
from backend.storage.sqlite import chunks as chunk_repo
from backend.storage.sqlite import documents as document_repo
from backend.storage.sqlite import sessions as session_repo

IR_PAYLOAD = {
    "document_id": "doc",
    "filename": "paper.pdf",
    "page_count": 1,
    "parser_name": "mineru",
    "parser_version": "2.1",
    "pages": [
        {
            "page_number": 1,
            "width": 600.0,
            "height": 800.0,
            "rotation": 0,
            "blocks": [
                {
                    "id": "b-1",
                    "page_number": 1,
                    "block_index": 0,
                    "type": "paragraph",
                    "text": "引用段落",
                    "reading_order": 0,
                    "section_path": ["1"],
                    "bbox": {"x0": 60.0, "y0": 80.0, "x1": 300.0, "y1": 160.0},
                }
            ],
        }
    ],
    "blocks": [],
    "outline": ["1"],
    "quality_report": {"parser_name": "mineru", "parser_version": "2.1", "page_count": 1},
}


def _seed(tmp_path: Path) -> tuple[str, str, Path]:
    session = session_repo.create_session("坐标测试")
    pdf_path = tmp_path / "data" / "raw" / session["id"] / "doc.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.7")

    document = document_repo.create_document(
        session_id=session["id"],
        filename="doc.pdf",
        file_path=str(pdf_path),
        mime_type="application/pdf",
        file_size=8,
    )
    artifact_dir = tmp_path / "data" / "parsed" / session["id"] / document["id"]
    artifact_dir.mkdir(parents=True, exist_ok=True)
    ir_path = artifact_dir / "document.ir.json"
    ir_path.write_text(json.dumps(IR_PAYLOAD), encoding="utf-8")

    document_repo.update_document_artifacts(
        document_id=document["id"],
        parsed_ir_path=str(ir_path),
        parsed_markdown_path=None,
        quality_report_path=None,
        parser_name="mineru",
        parser_version="2.1",
        parse_quality_status="good",
    )
    chunk_repo.insert_chunks(
        session["id"],
        document["id"],
        [
            Chunk(
                text="引用段落",
                metadata=ChunkMetadata(
                    paper_id=document["id"],
                    section="1",
                    chunk_index=0,
                    type="paragraph",
                    page_start=1,
                    page_end=1,
                    block_ids=["b-1", "missing-block"],
                ),
            )
        ],
    )
    return session["id"], document["id"], pdf_path


@pytest.mark.integration
def test_source_chunk_exposes_normalized_boxes(tmp_path):
    session_id, document_id, _ = _seed(tmp_path)

    result = get_source_chunk(session_id, document_id, 0)

    boxes = result["blocks"]
    assert [box["id"] for box in boxes] == ["b-1"]
    assert boxes[0]["page_number"] == 1
    assert boxes[0]["bbox"] == {"x0": 0.1, "y0": 0.1, "x1": 0.5, "y1": 0.2}


@pytest.mark.integration
def test_source_chunk_without_ir_yields_no_boxes(tmp_path):
    session_id, document_id, _ = _seed(tmp_path)
    document_repo.update_document_artifacts(
        document_id=document_id,
        parsed_ir_path=None,
        parsed_markdown_path=None,
        quality_report_path=None,
        parser_name=None,
        parser_version=None,
        parse_quality_status=None,
    )

    assert get_source_chunk(session_id, document_id, 0)["blocks"] == []


@pytest.mark.integration
def test_document_file_is_returned_for_owned_document(tmp_path):
    session_id, document_id, pdf_path = _seed(tmp_path)

    assert get_document_file(session_id, document_id) == pdf_path


@pytest.mark.integration
def test_document_file_rejects_paths_outside_data_dir(tmp_path):
    session_id, document_id, pdf_path = _seed(tmp_path)
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"%PDF-1.7")
    document_repo.create_document(
        session_id=session_id,
        filename="outside.pdf",
        file_path=str(outside),
        mime_type="application/pdf",
        file_size=8,
        document_id="outside-doc",
    )

    with pytest.raises(DocumentNotFoundError):
        get_document_file(session_id, "outside-doc")
    assert pdf_path.exists()
