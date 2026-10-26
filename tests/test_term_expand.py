"""Term expansion: the policy switches must work without any LLM call."""

import pytest

from backend.rag.retrieval.term_expander import term_expand


@pytest.mark.unit
def test_disabled_expansion_returns_the_query_untouched():
    assert term_expand("MoE 架构", {}, enabled=False) == ("MoE 架构", [], None)


@pytest.mark.unit
def test_llm_fallback_disabled_skips_expansion():
    query, keywords, source = term_expand("MoE 架构", {}, enabled=True, llm_fallback=False)

    assert query == "MoE 架构"
    assert keywords == []
    assert source is None


@pytest.mark.unit
def test_glossary_hit_is_used_without_the_llm():
    glossary = {"moe": ["mixture of experts"]}

    _query, keywords, source = term_expand("MoE 架构", glossary, llm_fallback=False)

    assert "mixture of experts" in keywords
    assert source == "glossary"
