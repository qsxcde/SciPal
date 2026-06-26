from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, Protocol


Language = Literal["zh", "en", "unknown"]
_MIXED_SCRIPT_RATIO = 0.2


class HasText(Protocol):
    text: str


@dataclass(frozen=True)
class LanguageDetection:
    language: Language
    confidence: float
    is_mixed: bool


def detect_language(text: str) -> LanguageDetection:
    """Detect Chinese or English from Han and Latin character ratios."""
    han_count, latin_count = _script_counts(text)
    supported_count = han_count + latin_count
    if not supported_count:
        return LanguageDetection(language="unknown", confidence=0.0, is_mixed=False)
    if han_count == latin_count:
        return LanguageDetection(language="unknown", confidence=0.5, is_mixed=True)

    language: Language = "zh" if han_count > latin_count else "en"
    confidence = max(han_count, latin_count) / supported_count
    minority_ratio = min(han_count, latin_count) / supported_count
    return LanguageDetection(
        language=language,
        confidence=confidence,
        is_mixed=minority_ratio >= _MIXED_SCRIPT_RATIO,
    )


def infer_document_language(chunks: Iterable[HasText]) -> Language:
    """Infer a document's dominant language from all chunk text."""
    han_count = 0
    latin_count = 0
    for chunk in chunks:
        chunk_han, chunk_latin = _script_counts(chunk.text)
        han_count += chunk_han
        latin_count += chunk_latin

    supported_count = han_count + latin_count
    if not supported_count or han_count == latin_count:
        return "unknown"
    return "zh" if han_count > latin_count else "en"


def _is_cjk(char: str) -> bool:
    """Check if char is CJK Unified Ideographs (main + Extension A-F)."""
    cp = ord(char)
    return (
        ("\u4e00" <= char <= "\u9fff")          # Main block
        or (0x3400 <= cp <= 0x4DBF)              # Extension A
        or (0x20000 <= cp <= 0x2A6DF)            # Extension B
        or (0x2A700 <= cp <= 0x2B73F)            # Extension C
        or (0x2B740 <= cp <= 0x2B81F)            # Extension D
        or (0x2B820 <= cp <= 0x2CEAF)            # Extension E
        or (0x2CEB0 <= cp <= 0x2EBEF)            # Extension F
    )


def _script_counts(text: str) -> tuple[int, int]:
    han_count = sum(_is_cjk(char) for char in text)
    latin_count = sum(("A" <= char <= "Z") or ("a" <= char <= "z") for char in text)
    return han_count, latin_count
