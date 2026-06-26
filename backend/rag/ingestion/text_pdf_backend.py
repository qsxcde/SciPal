from io import BytesIO

from backend.domain.config import settings
from backend.rag.ingestion.parser_backend import RawParserResult

FALLBACK_BLOCK_WORDS = 180


class TextPDFBackend:
    name = "pypdf-text"
    version = "unknown"

    def parse(self, pdf_bytes: bytes, filename: str | None = None) -> RawParserResult:
        from pypdf import PdfReader, PdfEncryptedError

        try:
            reader = PdfReader(BytesIO(pdf_bytes))
        except PdfEncryptedError:
            raise RuntimeError("PDF is encrypted and cannot be parsed")
        page_texts: list[str] = []
        pages: list[dict] = []
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                page_texts.append(text.strip())
                width = float(page.mediabox.width or 0)
                height = float(page.mediabox.height or 0)
                pages.append(
                    {
                        "page_number": index,
                        "width": width,
                        "height": height,
                        "rotation": int(page.rotation or 0),
                        "blocks": _blocks_for_page_text(
                            text=text,
                            page_number=index,
                            width=width,
                            height=height,
                        ),
                    }
                )
        markdown = "\n\n".join(page_texts)
        return RawParserResult(
            markdown=markdown,
            page_count=len(reader.pages),
            pages=pages,
            metadata={"filename": filename or ""},
            source_parser=self.name,
        )


def _blocks_for_page_text(
    *,
    text: str,
    page_number: int,
    width: float,
    height: float,
    max_words: int | None = None,
) -> list[dict]:
    words = text.strip().split()
    if not words:
        return []
    block_words = max_words or min(max(settings.max_chunk_tokens // 3, 80), FALLBACK_BLOCK_WORDS)
    blocks: list[dict] = []
    for offset in range(0, len(words), block_words):
        chunk_words = words[offset : offset + block_words]
        blocks.append(
            {
                "text": " ".join(chunk_words),
                "bbox": (0.0, 0.0, width, height),
                "type": "paragraph",
                "confidence": 0.5,
            }
        )
    return blocks
