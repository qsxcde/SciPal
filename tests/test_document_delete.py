"""文档删除：行、分块、磁盘产物与索引刷新。"""

from pathlib import Path

import pytest

from backend.application import index_maintenance
from backend.application.documents import delete_document
from backend.domain.exceptions import DocumentNotFoundError, JobInProgressError
from backend.domain.states import DocumentStage
from backend.storage.sqlite import jobs as job_repo
from backend.domain.models import Chunk, ChunkMetadata
from backend.storage.sqlite import chunks as chunk_repo
from backend.storage.sqlite import documents as document_repo
from backend.storage.sqlite import sessions as session_repo


def _seed(tmp_path: Path) -> tuple[str, str, Path]:
    session = session_repo.create_session("删除测试")
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
    ir_path.write_text("{}", encoding="utf-8")

    document_repo.update_document_artifacts(
        document_id=document["id"],
        parsed_ir_path=str(ir_path),
        parsed_markdown_path=str(artifact_dir / "document.md"),
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
                text="内容",
                metadata=ChunkMetadata(
                    paper_id=document["id"],
                    section="1",
                    chunk_index=0,
                    type="paragraph",
                ),
            )
        ],
    )
    return session["id"], document["id"], artifact_dir


@pytest.mark.integration
def test_delete_removes_rows_files_and_refreshes_index(tmp_path, monkeypatch):
    session_id, document_id, artifact_dir = _seed(tmp_path)
    refreshed: list[str] = []
    monkeypatch.setattr(index_maintenance, "refresh_after_document_change", refreshed.append)

    delete_document(session_id, document_id)

    assert document_repo.get_document(document_id) is None
    assert chunk_repo.list_chunks(session_id) == []
    assert not artifact_dir.exists()
    assert refreshed == [session_id]


@pytest.mark.integration
def test_delete_is_scoped_to_session(tmp_path, monkeypatch):
    _, document_id, _ = _seed(tmp_path)
    other = session_repo.create_session("另一个会话")
    monkeypatch.setattr(index_maintenance, "refresh_after_document_change", lambda _sid: None)

    with pytest.raises(DocumentNotFoundError):
        delete_document(other["id"], document_id)

    assert document_repo.get_document(document_id) is not None


@pytest.mark.integration
def test_rebuild_failure_invalidates_index(tmp_path, monkeypatch):
    session_id, document_id, _ = _seed(tmp_path)

    def boom(_session_id: str) -> None:
        raise RuntimeError("faiss down")

    invalidated: list[tuple[str, str]] = []
    monkeypatch.setattr(index_maintenance, "refresh_after_document_change", boom)
    monkeypatch.setattr(
        index_maintenance,
        "invalidate_session_index",
        lambda sid, reason: invalidated.append((sid, reason)),
    )

    delete_document(session_id, document_id)

    assert document_repo.get_document(document_id) is None
    assert invalidated == [(session_id, "索引重建失败")]


@pytest.mark.integration
def test_delete_is_rejected_while_the_session_is_ingesting(tmp_path: Path):
    session_id, document_id, _pdf = _seed(tmp_path)
    job = job_repo.create_job(
        session_id=session_id,
        document_id=document_id,
        job_type="document_ingestion",
        stage=DocumentStage.uploaded,
    )
    assert job_repo.mark_job_running(job["id"]) is True

    with pytest.raises(JobInProgressError):
        delete_document(session_id, document_id)

    assert document_repo.get_document(document_id) is not None
