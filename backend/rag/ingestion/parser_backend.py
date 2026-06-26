from typing import Protocol

from pydantic import BaseModel, Field


class RawParserResult(BaseModel):
    markdown: str
    page_count: int
    pages: list[dict] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    source_parser: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ParserBackend(Protocol):
    name: str
    version: str

    def parse(self, pdf_bytes: bytes, filename: str | None = None) -> RawParserResult:
        """Parse PDF bytes into raw text and layout data."""
