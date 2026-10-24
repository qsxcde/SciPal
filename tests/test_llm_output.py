"""LLM payload normalisation shared by rewriting, expansion and judging."""

import pytest

from backend.rag.llm_output import parse_json_object, strip_markdown_fence


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"a": 1}', '{"a": 1}'),
        ('```json\n{"a": 1}\n```', '{"a": 1}'),
        ('```\n{"a": 1}\n```', '{"a": 1}'),
        ('```json {"a": 1}```', '{"a": 1}'),
        ('  ```JSON\n  {"a": 1}\n```  ', '{"a": 1}'),
    ],
)
def test_strip_markdown_fence_variants(raw, expected):
    assert strip_markdown_fence(raw) == expected


@pytest.mark.unit
def test_parse_json_object_accepts_fenced_payload():
    assert parse_json_object('```json\n{"terms": []}\n```') == {"terms": []}


@pytest.mark.unit
def test_parse_json_object_rejects_non_object():
    with pytest.raises(ValueError):
        parse_json_object("[1, 2, 3]")


@pytest.mark.unit
def test_parse_json_object_rejects_invalid_json():
    with pytest.raises(ValueError):
        parse_json_object("not json at all")
