"""Multi-turn history-aware query rewriting for retrieval.

Rewrites the current user query to include context from previous turns,
resolving anaphora and filling in omitted references.
"""

from __future__ import annotations

import logging
from functools import lru_cache
import importlib.resources
import tomllib

from backend.domain.config import settings
from backend.rag.generation.llm import complete_text

logger = logging.getLogger(__name__)


_ANAPHORA_MARKERS_ZH = {"它", "其", "该", "这", "那", "两者", "两者都", "上述", "上文", "前者", "后者", "以上"}
_ANAPHORA_MARKERS_EN = {"it", "its", "they", "them", "their", "this", "that", "these", "those"}


@lru_cache(maxsize=1)
def _load_history_rewrite_prompt() -> str:
    """Load history rewrite prompt from prompts.toml."""
    path = importlib.resources.files("backend.prompts") / "prompts.toml"
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)["history_rewrite"]["system"]
    except Exception:
        logger.exception("Failed to load history_rewrite prompt from %s", path)
        return _FALLBACK_PROMPT


_FALLBACK_PROMPT = """You are a query rewriting assistant for an academic paper Q&A system.
Given the conversation history and the current user query,
rewrite the current query into a self-contained, retrieval-optimized query
that includes all necessary context from the history.

Rules:
1. Resolve anaphora: "it" → the paper/model/method mentioned, "they" → the authors/models
2. Fill in omitted context: if history discussed "MoE vs Dense", and user asks "对比两者的 training efficiency",
   rewrite as "对比 MoE 和 Dense 架构的 training efficiency"
3. Keep technical terms, abbreviations, author names, model names, numbers, and metrics unchanged
4. Output ONLY the rewritten query text, no explanations, no formatting

Conversation history (oldest first):
{history}

Current query: {query}

Rewritten query:"""


def _has_anaphora(query: str) -> bool:
    """Check if query contains anaphoric references needing history context."""
    query_lower = query.lower()
    for marker in _ANAPHORA_MARKERS_ZH:
        if marker in query:
            return True
    for marker in _ANAPHORA_MARKERS_EN:
        if marker in query_lower:
            return True
    return False


def _should_rewrite(query: str, history: list[dict]) -> bool:
    """Determine if history-aware rewrite is needed."""
    if not history:
        return False
    if _has_anaphora(query):
        return True
    if len(query) < settings.history_rewrite_min_query_length:
        return True
    return False


def _format_history(
    history: list[dict],
    max_rounds: int,
) -> str:
    """Format history turns into a text block for the rewrite prompt."""
    lines: list[str] = []
    relevant = history[-(max_rounds * 2):]
    for msg in relevant:
        role = msg.get("role", "unknown")
        content = msg.get("content", "").strip()
        if not content:
            continue
        label = "User" if role == "user" else "Assistant"
        lines.append(f"{label}: {content}")
    return "\n".join(lines)


def build_rewrite_prompt(
    query: str,
    history_text: str,
) -> str:
    template = _load_history_rewrite_prompt()
    return template.format(history=history_text, query=query)


@lru_cache(maxsize=128)
def _cached_rewrite(query: str, history_text: str) -> str:
    """Call LLM to rewrite query with history context. Cached for identical inputs."""
    prompt = build_rewrite_prompt(query, history_text)
    try:
        raw = complete_text(prompt)
        result = raw.strip().strip('"').strip("'")
        return result if result else query
    except Exception:
        logger.exception("history_aware_rewrite failed for query=%r", query)
        return query


def history_aware_rewrite(
    current_query: str,
    history: list[dict],
    max_rounds: int | None = None,
) -> str:
    """Rewrite current query with multi-turn context awareness.

    Args:
        current_query: The user's latest query.
        history: List of previous messages with 'role' and 'content' keys,
                 ordered oldest to newest. Only user and assistant messages
                 from prior turns should be included (not the current query).
        max_rounds: Max conversation rounds to consider (default from config).

    Returns:
        Self-contained rewritten query, or original query if no rewrite needed.
    """
    if not settings.history_rewrite_enabled:
        return current_query
    if not _should_rewrite(current_query, history):
        return current_query

    rounds = max_rounds if max_rounds is not None else settings.history_rewrite_max_rounds
    history_text = _format_history(history, rounds)
    if not history_text:
        return current_query

    return _cached_rewrite(current_query, history_text)
