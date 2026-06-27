import re

from pydantic import BaseModel

from backend.domain.exceptions import PaperParseError
from backend.rag.ingestion.chunking import build_chunks
from backend.rag.ingestion.document_ir import DocumentIR
from backend.rag.ingestion.document_ir import QualityReport
from backend.rag.ingestion.exporters import export_markdown
from backend.rag.ingestion.metadata import Chunk, ChunkMetadata
from backend.rag.ingestion.mineru_backend import MinerUBackend
from backend.rag.ingestion.normalizer import normalize_parser_output
from backend.rag.ingestion.parser_backend import ParserBackend
from backend.rag.ingestion.parser_backend import RawParserResult
from backend.rag.ingestion.text_pdf_backend import TextPDFBackend


def _safe_paper_id(paper_id: str) -> str:
    """Sanitize paper_id to avoid filesystem issues (Windows reserved chars, etc.)."""
    cleaned = re.sub(r'[<>:"/\\|?*]', "_", paper_id)
    return cleaned or "_"


class IngestionResult(BaseModel):
    document_ir: DocumentIR
    raw_markdown: str
    markdown: str
    quality_report: QualityReport
    chunks: list[Chunk]


def process_pdf(pdf_bytes: bytes, paper_id: str) -> list[Chunk]:
    return process_pdf_document(
        pdf_bytes=pdf_bytes,
        paper_id=paper_id,
        filename=f"{paper_id}.pdf",
    ).chunks


def process_pdf_document(
    pdf_bytes: bytes,
    paper_id: str,
    filename: str,
    parser_backend: ParserBackend | None = None,
) -> IngestionResult:
    backend = parser_backend or MinerUBackend()
    try:
        raw: RawParserResult = backend.parse(pdf_bytes, filename=filename)
    except Exception as exc:
        if parser_backend is not None:
            raise PaperParseError(f"Failed to parse PDF: {exc}") from exc
        backend = TextPDFBackend()
        try:
            raw = backend.parse(pdf_bytes, filename=filename)
        except Exception:
            raise PaperParseError(f"Failed to parse PDF: {exc}") from exc

    document_ir = normalize_parser_output(
        raw=raw,
        paper_id=paper_id,
        filename=filename,
        parser_backend=backend,
    )
    if not raw.markdown.strip() and not any(block.text.strip() for block in document_ir.blocks):
        raise PaperParseError(
            "PDF_TEXT_NOT_EXTRACTABLE: 当前版本仅支持可复制文本的 PDF，不支持扫描版或图片型 PDF"
        )

    normalized_markdown = export_markdown(document_ir)
    chunks = build_chunks(document_ir=document_ir, markdown=normalized_markdown, paper_id=paper_id)
    if not chunks and raw.markdown.strip():
        normalized_markdown = raw.markdown.strip() + "\n"
        chunks = build_chunks(document_ir=document_ir, markdown=normalized_markdown, paper_id=paper_id)
    if not chunks:
        headings = [b.text.strip() for b in document_ir.blocks if b.type in {"heading", "title"}]
        if headings:
            fallback_chunk = Chunk(
                text=headings[0],
                metadata=ChunkMetadata(
                    paper_id=paper_id,
                    section="Abstract",
                    section_path=["Abstract"],
                    chunk_index=0,
                    type="paragraph",
                    page_start=1,
                    page_end=1,
                    confidence=0.3,
                ),
            )
            chunks = [fallback_chunk]
        else:
            raise PaperParseError(
                "NO_RETRIEVABLE_CHUNKS: 论文解析结果缺少可检索正文片段，当前无法建立 RAG 索引"
            )
    return IngestionResult(
        document_ir=document_ir,
        raw_markdown=raw.markdown,
        markdown=normalized_markdown,
        quality_report=document_ir.quality_report,
        chunks=chunks,
    )
