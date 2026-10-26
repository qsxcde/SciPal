"""Guard: every RuntimeSettings field must appear in the configuration wiki."""

from pathlib import Path


def doc_path() -> Path:
    return Path(__file__).resolve().parents[4] / "docs" / "wiki" / "08-configuration.md"


def documented_env_names(text: str) -> set[str]:
    """Env names mentioned anywhere in the document (tables or prose)."""
    import re

    return set(re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", text))


def missing_fields(text: str, field_names: list[str]) -> list[str]:
    documented = documented_env_names(text)
    return [name for name in field_names if name.upper() not in documented]
