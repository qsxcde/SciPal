import logging
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.composition import text_completer
from backend.prompts.loader import load_prompt
from backend.rag.llm_output import parse_json_object

logger = logging.getLogger(__name__)


class QueryPack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    translated_query: str
    retrieval_query: str
    keywords: list[str] = Field(default_factory=list)

    @field_validator("translated_query", "retrieval_query")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query fields must be non-empty")
        return value


def fallback_query_pack(query: str) -> QueryPack:
    return QueryPack(
        translated_query=query,
        retrieval_query=query,
        keywords=[],
    )


def build_query_rewrite_prompt(
    query: str,
    source_language: str,
    target_language: str,
) -> str:
    return load_prompt("query_rewrite").format(
        source_language=source_language,
        target_language=target_language,
        query=query,
    )


def generate_query_pack(
    query: str,
    source_language: str,
    target_language: str,
    complete: Callable[[str], str] | None = None,
) -> QueryPack:
    prompt = build_query_rewrite_prompt(query, source_language, target_language)
    completion = complete or text_completer().complete
    try:
        payload = parse_json_object(completion(prompt))
        payload.setdefault("keywords", [])
        return QueryPack.model_validate(payload)
    except Exception:
        logger.exception("generate_query_pack failed for query=%r", query)
        return fallback_query_pack(query)
