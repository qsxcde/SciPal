from pathlib import Path

import pytest

from backend.app.main import app
from backend.domain import config as runtime_config
from backend.rag.ingestion.metadata import Chunk, ChunkMetadata
from backend.rag.ingestion.document_ir import DocumentIR, PageIR, QualityReport
from backend.rag.ingestion.pipeline import IngestionResult

pytestmark = pytest.mark.integration


def _fake_ingestion_result(paper_id: str, filename: str, text: str) -> IngestionResult:
    quality_report = QualityReport(
        parser_name="fake",
        parser_version="1",
        page_count=1,
        text_block_count=1,
        overall_status="good",
    )
    return IngestionResult(
        document_ir=DocumentIR(
            document_id=paper_id,
            filename=filename,
            page_count=1,
            parser_name="fake",
            parser_version="1",
            pages=[PageIR(page_number=1, width=100.0, height=200.0, rotation=0, blocks=[])],
            blocks=[],
            outline=[],
            quality_report=quality_report,
        ),
        raw_markdown=f"# {filename}\n\n{text}\n",
        markdown=f"# {filename}\n\n{text}\n",
        quality_report=quality_report,
        chunks=[
            Chunk(
                text=text,
                metadata=ChunkMetadata(
                    paper_id=paper_id,
                    section="摘要",
                    chunk_index=0,
                    type="paragraph",
                    section_path=["摘要"],
                    page_start=1,
                    page_end=1,
                    block_ids=["p1-b0"],
                    confidence=0.9,
                ),
            )
        ],
    )


def test_get_store_rebuilds_from_persisted_chunks_when_no_ready_snapshot_exists(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setattr(runtime_config.settings, "scipal_data_dir", str(tmp_path))

    from backend.storage.sqlite import chunks as chunk_repo
    from backend.storage.sqlite import documents as document_repo
    from backend.storage.sqlite import schema
    from backend.storage.sqlite import sessions as session_repo
    from backend.rag.indexing import vector_store as faiss_store
    from backend.storage.vector_db import registry as index_registry

    schema.init_db()
    index_registry.clear_cache()

    def fake_embed(texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(faiss_store, "_default_embed", fake_embed)

    session = session_repo.create_session("chunk-only session")
    document = document_repo.create_document(
        session_id=session["id"],
        filename="paper.pdf",
        file_path=str(tmp_path / "paper.pdf"),
        mime_type="application/pdf",
        file_size=16,
    )
    chunk_repo.insert_chunks(
        session_id=session["id"],
        document_id=document["id"],
        parsed_chunks=[
            Chunk(
                text="chunk-only text",
                metadata=ChunkMetadata(
                    paper_id=document["id"],
                    section="摘要",
                    chunk_index=0,
                    type="paragraph",
                    section_path=["摘要"],
                ),
            )
        ],
    )
    document_repo.update_document_status(document["id"], "ready", chunk_count=1)

    store = index_registry.get_store(session["id"])
    second_document = document_repo.create_document(
        session_id=session["id"],
        filename="paper-two.pdf",
        file_path=str(tmp_path / "paper-two.pdf"),
        mime_type="application/pdf",
        file_size=32,
    )
    chunk_repo.insert_chunks(
        session_id=session["id"],
        document_id=second_document["id"],
        parsed_chunks=[
            Chunk(
                text="second chunk-only text",
                metadata=ChunkMetadata(
                    paper_id=second_document["id"],
                    section="方法",
                    chunk_index=0,
                    type="paragraph",
                    section_path=["方法"],
                ),
            )
        ],
    )
    document_repo.update_document_status(second_document["id"], "ready", chunk_count=1)
    rebuilt_store = index_registry.get_store(session["id"])

    assert [chunk.metadata.paper_id for chunk in store.list_chunks()] == [document["id"]]
    assert [chunk.metadata.paper_id for chunk in rebuilt_store.list_chunks()] == [
        document["id"],
        second_document["id"],
    ]

def test_candidate_snapshot_excludes_reference_chunks_from_index(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setattr(runtime_config.settings, "scipal_data_dir", str(tmp_path))

    from backend.storage.sqlite import chunks as chunk_repo
    from backend.storage.sqlite import documents as document_repo
    from backend.storage.sqlite import schema
    from backend.storage.sqlite import sessions as session_repo
    from backend.rag.indexing import vector_store as faiss_store
    from backend.app.services import index_service as index_app_service
    from backend.storage.vector_db import registry as index_registry

    schema.init_db()
    index_registry.clear_cache()

    def fake_embed(texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(faiss_store, "_default_embed", fake_embed)

    session = session_repo.create_session("reference-filter session")
    document = document_repo.create_document(
        session_id=session["id"],
        filename="paper.pdf",
        file_path=str(tmp_path / "paper.pdf"),
        mime_type="application/pdf",
        file_size=16,
    )
    chunk_repo.insert_chunks(
        session_id=session["id"],
        document_id=document["id"],
        parsed_chunks=[
            Chunk(
                text="The proposed method denoises visual representations.",
                metadata=ChunkMetadata(
                    paper_id=document["id"],
                    section="3 Methods",
                    chunk_index=0,
                    type="paragraph",
                    section_path=["3 Methods"],
                ),
            ),
            Chunk(
                text="A. Author. Prior work. 2024.",
                metadata=ChunkMetadata(
                    paper_id=document["id"],
                    section="References",
                    chunk_index=1,
                    type="paragraph",
                    section_path=["References"],
                ),
            ),
        ],
    )

    snapshot = index_app_service.build_candidate_snapshot(
        session_id=session["id"],
        document_id=document["id"],
    )
    store = faiss_store.FAISSVectorStore.load(
        index_path=Path(snapshot["index_path"]),
        chunks_path=Path(snapshot["chunks_path"]),
    )

    assert [chunk.metadata.section for chunk in store.list_chunks()] == ["3 Methods"]

def test_get_store_hides_unpublished_chunks_during_first_document_ingestion(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setattr(runtime_config.settings, "scipal_data_dir", str(tmp_path))

    from backend.storage.sqlite import documents as document_repo
    from backend.storage.sqlite import jobs as job_repo
    from backend.storage.sqlite import schema
    from backend.rag.indexing import vector_store as faiss_store
    from backend.app.services.document_service import intake_document_upload
    from backend.app.services import ingestion_service
    from backend.app.services import index_service as index_app_service
    from backend.app.services.job_runner import InProcessJobRunner
    from backend.storage.vector_db import registry as index_registry
    from fastapi.testclient import TestClient

    schema.init_db()
    index_registry.clear_cache()

    def fake_embed(texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    def fake_process_pdf_document(
        pdf_bytes: bytes,
        paper_id: str,
        filename: str,
    ) -> IngestionResult:
        return _fake_ingestion_result(
            paper_id=paper_id,
            filename=filename,
            text="first document hidden chunk",
        )

    monkeypatch.setattr(faiss_store, "_default_embed", fake_embed)
    monkeypatch.setattr(
        "backend.app.services.ingestion_service.process_pdf_document",
        fake_process_pdf_document,
    )

    observed_store_document_ids: list[str] = []
    real_build_candidate_snapshot = index_app_service.build_candidate_snapshot

    def inspect_during_chunked(session_id: str, document_id: str):
        index_registry.clear_cache()
        observed_store = index_registry.get_store(session_id)
        observed_store_document_ids[:] = [
            chunk.metadata.paper_id for chunk in observed_store.list_chunks()
        ]
        return real_build_candidate_snapshot(session_id, document_id)

    monkeypatch.setattr(ingestion_service, "build_candidate_snapshot", inspect_during_chunked)

    client = TestClient(app, raise_server_exceptions=False)
    session_id = client.post("/sessions").json()["session_id"]
    runner = InProcessJobRunner()

    intake = intake_document_upload(
        session_id=session_id,
        filename="paper.pdf",
        mime_type="application/pdf",
        pdf_bytes=b"%PDF hidden chunk",
    )

    assert runner.tick() == 1

    finished_job = job_repo.get_job(intake["job"]["id"])
    finished_document = document_repo.get_document(intake["document"]["id"])

    assert finished_job is not None
    assert finished_document is not None
    assert finished_job["status"] == "succeeded"
    assert finished_document["status"] == "ready"
    assert observed_store_document_ids == []
