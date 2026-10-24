"""Single loader for prompt templates stored in ``prompts.toml``.

Every prompt consumer goes through :func:`load_prompt` so that the file path,
parsing and caching rules live in exactly one place.
"""

from functools import cache
import importlib.resources
import tomllib

PROMPT_FILE = "prompts.toml"
DEFAULT_KEY = "system"


@cache
def _load_prompt_file() -> dict:
    path = importlib.resources.files("backend.prompts") / PROMPT_FILE
    with path.open("rb") as handle:
        return tomllib.load(handle)


def load_prompt(
    section: str,
    *,
    key: str = DEFAULT_KEY,
    default: str | None = None,
) -> str:
    """Return ``prompts.toml[section][key]``.

    When the section is missing, ``default`` is returned if provided; otherwise
    a ``KeyError`` is raised so configuration mistakes fail loudly.
    """
    prompts = _load_prompt_file()
    block = prompts.get(section)
    if not isinstance(block, dict) or key not in block:
        if default is not None:
            return default
        raise KeyError(f"Missing prompt section {section!r} (key {key!r}) in {PROMPT_FILE}")
    value = block[key]
    if not isinstance(value, str):
        raise TypeError(f"Prompt {section!r}.{key!r} must be a string, got {type(value).__name__}")
    return value
