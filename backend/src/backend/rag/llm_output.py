"""Normalise structured payloads returned by LLM providers.

LLMs routinely wrap JSON in Markdown fences. This module is the single place
that knows how to unwrap and validate such payloads.
"""

import json
from typing import Any


def strip_markdown_fence(text: str) -> str:
    """Remove a surrounding ```json ... ``` (or ``` ... ```) fence."""
    cleaned = text.strip()
    if not cleaned.startswith("```"):
        return cleaned

    newline = cleaned.find("\n")
    if newline == -1:
        # Single-line payload: ```json {"a": 1}```
        body = cleaned[3:]
        if body[:4].lower() == "json":
            body = body[4:]
        return body.strip().strip("`").strip()

    body = cleaned[newline + 1 :]
    stripped_tail = body.rstrip()
    if stripped_tail.endswith("```"):
        body = stripped_tail[:-3]
    return body.strip()


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object out of raw LLM output.

    Raises ``ValueError`` when the payload is not a JSON object, so callers can
    keep a single ``except`` branch for "the model misbehaved".
    """
    payload = json.loads(strip_markdown_fence(text))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object, got {type(payload).__name__}")
    return payload
