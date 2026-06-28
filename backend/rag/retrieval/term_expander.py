"""Academic term expansion for retrieval queries.

Provides glossary-based and LLM-driven term expansion to improve
retrieval recall on specialized academic abbreviations and terms.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
import tomllib

from backend.domain.config import settings
from backend.rag.generation.llm import complete_text

logger = logging.getLogger(__name__)


_UPPER_ABBREV_RE = re.compile(r"\b[A-Z]{2,6}\b")


def load_glossary() -> dict[str, list[str]]:
    """Load term glossary from JSON file. Returns empty dict on failure."""
    from backend.domain.config import project_root
    raw_path = settings.term_expand_glossary_path
    path = Path(raw_path)
    if not path.is_absolute():
        path = project_root() / raw_path
    if not path.exists():
        logger.warning("Term glossary not found at %s, skipping", path)
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return dict[str, list[str]](json.load(f))
    except Exception:
        logger.exception("Failed to load term glossary from %s", path)
        return {}


def _match_glossary(
    query: str,
    glossary: dict[str, list[str]],
) -> list[str]:
    """Case-insensitive term matching. Returns extra keywords for matched terms."""
    query_lower = query.lower()
    extra: list[str] = []
    for term, expansions in glossary.items():
        if term.lower() in query_lower:
            for exp in expansions:
                exp_lower = exp.lower()
                if exp_lower not in query_lower:
                    extra.append(exp)
    return extra


def _count_glossary_matches(query: str, glossary: dict[str, list[str]]) -> int:
    """Count how many glossary terms appear in the query."""
    query_lower = query.lower()
    return sum(1 for term in glossary if term.lower() in query_lower)


def _needs_llm_expansion(query: str, glossary: dict[str, list[str]]) -> bool:
    """Determine if LLM term expansion is warranted.

    Triggers when:
    - Query length > 5 chars with no glossary matches (possibly unseen terms)
    - Query contains uppercase abbreviation patterns not in glossary
    """
    if not settings.term_expand_llm_fallback:
        return False

    # Heuristic 1: Long query with zero glossary matches
    if len(query) > 5 and _count_glossary_matches(query, glossary) == 0:
        return True

    # Heuristic 2: Uppercase abbreviation not in glossary (e.g., LLM, MoE, DPO)
    if _UPPER_ABBREV_RE.search(query):
        for match in _UPPER_ABBREV_RE.finditer(query):
            term = match.group().lower()
            if term not in glossary:
                return True

    return False


@lru_cache(maxsize=1)
def _load_term_expand_prompt() -> str:
    """Load term expand prompt from prompts.toml."""
    path = Path(__file__).resolve().parents[2] / "prompts" / "prompts.toml"
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)["term_expand"]["system"]
    except Exception:
        logger.exception("Failed to load term_expand prompt from %s", path)
        return _FALLBACK_TERM_PROMPT


_FALLBACK_TERM_PROMPT = """Identify any academic/technical abbreviations or specialized terms in the user query
that may not be resolved correctly by a semantic search engine.
For each identified term, provide 2-3 alternative phrasings or expanded forms.

Focus on:
- Abbreviations (LLM → large language model, MoE → mixture of experts)
- Naming (Qwen → Qwen model series by Alibaba)
- Methodology names (RLHF → reinforcement learning from human feedback)

Return JSON:
{{"terms": [{{"original": "...", "expansions": ["...", "..."]}}]}}

Query: {query}
"""


def build_term_expand_prompt(query: str) -> str:
    template = _load_term_expand_prompt()
    return template.format(query=query)


def _strip_markdown_fence(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` markdown fences from LLM output."""
    text = re.sub(r"^```(?:json)?\s*\n?", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\n```\s*$", "", text, flags=re.MULTILINE)
    return text.strip()


@lru_cache(maxsize=64)
def _cached_llm_expand(query: str) -> list[str]:
    """Call LLM to identify and expand academic terms. Cached for identical queries."""
    prompt = build_term_expand_prompt(query)
    try:
        raw = complete_text(prompt)
        payload = json.loads(_strip_markdown_fence(raw))
        terms = payload.get("terms", [])
        result: list[str] = []
        for entry in terms:
            result.extend(entry.get("expansions", []))
        return result
    except Exception:
        logger.exception("llm_term_expand failed for query=%r", query)
        return []


def term_expand(
    query: str,
    glossary: dict[str, list[str]] | None = None,
) -> tuple[str, list[str], str | None]:
    """Expand query with academic term alternatives.

    Phase 1: Static glossary match (fast, covers common terms).
    Phase 2: LLM fallback for unmatched abbreviations (only when needed).

    Args:
        query: The user's query (already history-rewritten if applicable).
        glossary: Optional pre-loaded glossary. Loads from config path if None.

    Returns:
        Tuple of (original_query, extra_keywords, expand_source).
        expand_source is "glossary", "glossary+llm", or None.
    """
    if not settings.term_expand_enabled:
        return query, [], None

    effective_glossary = glossary if glossary is not None else load_glossary()
    extra_keywords: list[str] = _match_glossary(query, effective_glossary)
    used_llm = False

    if _needs_llm_expansion(query, effective_glossary):
        llm_keywords = _cached_llm_expand(query)
        if llm_keywords:
            used_llm = True
            extra_keywords.extend(llm_keywords)

    # Deduplicate while preserving order
    seen = set()
    deduped: list[str] = []
    for kw in extra_keywords:
        lower = kw.lower()
        if lower not in seen:
            seen.add(lower)
            deduped.append(kw)

    expand_source: str | None = None
    if deduped:
        expand_source = "glossary+llm" if used_llm else "glossary"

    return query, deduped, expand_source
