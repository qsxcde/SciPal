import json
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from backend.rag.generation.llm import complete_text


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
    return (
        "Rewrite the user query into a retrieval-ready query pack.\n"
        f"Source language: {source_language}\n"
        f"Target language: {target_language}\n"
        "Return JSON only with this exact contract:\n"
        "{"
        '"translated_query": "string", '
        '"retrieval_query": "string", '
        '"keywords": ["string"]'
        "}\n"
        "Do not add extra fields. Preserve meaning, translate for the target language, "
        "and keep proper nouns, abbreviations, author names, model names, numbers, metrics, "
        "and units unchanged. 专有名词、缩写、作者名、模型名、数字、指标、单位必须原样保留。 "
        "and keep retrieval_query optimized for search.\n"
        f"User query: {query}"
    )


def _strip_markdown_fence(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` markdown fences from LLM output."""
    import re
    text = re.sub(r"^```(?:json)?\s*\n?", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\n```\s*$", "", text, flags=re.MULTILINE)
    return text.strip()


def generate_query_pack(
    query: str,
    source_language: str,
    target_language: str,
    complete: Callable[[str], str] | None = None,
) -> QueryPack:
    prompt = build_query_rewrite_prompt(query, source_language, target_language)
    completion = complete or complete_text
    try:
        raw = completion(prompt)
        payload = json.loads(_strip_markdown_fence(raw))
        if "keywords" not in payload:
            payload["keywords"] = []
        return QueryPack.model_validate(payload)
    except Exception:
        return fallback_query_pack(query)
