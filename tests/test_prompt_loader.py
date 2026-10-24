"""All prompt consumers read prompts.toml through one loader."""

import pytest

from backend.prompts.loader import load_prompt


@pytest.mark.unit
def test_loads_declared_sections():
    assert "论文助手" in load_prompt("rag_answer")
    assert "translated_query" in load_prompt("query_rewrite")
    assert "Rewritten query" in load_prompt("history_rewrite")
    assert "abbreviations" in load_prompt("term_expand")


@pytest.mark.unit
def test_missing_section_returns_default():
    assert load_prompt("does_not_exist", default="fallback") == "fallback"


@pytest.mark.unit
def test_missing_section_without_default_raises():
    with pytest.raises(KeyError):
        load_prompt("does_not_exist")


@pytest.mark.unit
def test_missing_key_returns_default():
    assert load_prompt("rag_answer", key="does_not_exist", default="fallback") == "fallback"
