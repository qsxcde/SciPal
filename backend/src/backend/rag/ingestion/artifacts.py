import json
from pathlib import Path

from pydantic import BaseModel

from backend.rag.ingestion.document_ir import DocumentIR, QualityReport


class IngestionArtifacts(BaseModel):
    ir_path: Path
    markdown_path: Path
    normalized_markdown_path: Path
    quality_report_path: Path


def save_ingestion_artifacts(
    artifact_dir: Path,
    document_ir: DocumentIR,
    raw_markdown: str,
    normalized_markdown: str,
    quality_report: QualityReport,
) -> IngestionArtifacts:
    """Persist parser artifacts for cache, inspection, and repeatable RAG ingestion."""
    artifact_dir.mkdir(parents=True, exist_ok=True)
    ir_path = artifact_dir / "document.ir.json"
    markdown_path = artifact_dir / "document.md"
    normalized_markdown_path = artifact_dir / "document.normalized.md"
    quality_report_path = artifact_dir / "quality_report.json"
    source_markdown = raw_markdown.strip() or normalized_markdown

    ir_path.write_text(_json_dump(document_ir.model_dump(mode="json")), encoding="utf-8")
    markdown_path.write_text(source_markdown.rstrip() + "\n", encoding="utf-8")
    normalized_markdown_path.write_text(normalized_markdown.rstrip() + "\n", encoding="utf-8")
    quality_report_path.write_text(_json_dump(quality_report.model_dump(mode="json")), encoding="utf-8")

    return IngestionArtifacts(
        ir_path=ir_path,
        markdown_path=markdown_path,
        normalized_markdown_path=normalized_markdown_path,
        quality_report_path=quality_report_path,
    )


def _json_dump(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
