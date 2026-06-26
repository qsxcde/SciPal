from backend.rag.ingestion.pipeline import IngestionResult
from backend.rag.ingestion.pipeline import process_pdf_document


def process_document_offline(
    pdf_bytes: bytes,
    paper_id: str,
    filename: str,
) -> IngestionResult:
    return process_pdf_document(
        pdf_bytes=pdf_bytes,
        paper_id=paper_id,
        filename=filename,
    )
