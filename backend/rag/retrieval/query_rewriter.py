import json
from collections.abc import Callable
from functools import cache
from pathlib import Path
import tomllib

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


@cache
def _load_query_rewrite_prompt() -> str:
    path = Path(__file__).resolve().parents[2] / "prompts" / "prompts.toml"
    with open(path, "rb") as f:
        return tomllib.load(f)["query_rewrite"]["system"]


def build_query_rewrite_prompt(
    query: str,
    source_language: str,
    target_language: str,
) -> str:
    return _load_query_rewrite_prompt().format(
        source_language=source_language,
        target_language=target_language,
        query=query,
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
