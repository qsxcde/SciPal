"""Regenerate the README endpoint table from contracts/openapi.json.

Hand-maintained endpoint lists drift: the README advertised 7 endpoints while
the app served 15. The table is now derived, and a test fails when it is stale.
"""

import json
from pathlib import Path

START = "<!-- api-endpoints:start -->"
END = "<!-- api-endpoints:end -->"


def readme_path() -> Path:
    return Path(__file__).resolve().parents[4] / "README.md"


def openapi_path() -> Path:
    return Path(__file__).resolve().parents[4] / "contracts" / "openapi.json"


def _describe(operation: dict) -> str:
    description = (operation.get("description") or "").strip().splitlines()
    if description:
        return description[0].strip()
    return operation.get("summary") or ""


def render_table(schema: dict) -> str:
    """Render a markdown table of every documented operation."""
    rows = ["| 方法 | 路径 | 说明 |", "|---|---|---|"]
    for path, operations in sorted(schema.get("paths", {}).items()):
        for method, operation in sorted(operations.items()):
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            description = _describe(operation).replace("|", "\\|")
            rows.append(f"| {method.upper()} | `{path}` | {description} |")
    return "\n".join(rows)


def render_block(schema: dict) -> str:
    return f"{START}\n{render_table(schema)}\n{END}"


def update_readme(schema: dict | None = None) -> bool:
    """Rewrite the marked block; returns True when the file changed."""
    if schema is None:
        schema = json.loads(openapi_path().read_text(encoding="utf-8"))
    readme = readme_path()
    text = readme.read_text(encoding="utf-8")
    start = text.index(START)
    end = text.index(END) + len(END)
    updated = text[:start] + render_block(schema) + text[end:]
    if updated == text:
        return False
    readme.write_text(updated, encoding="utf-8")
    return True


if __name__ == "__main__":
    changed = update_readme()
    print("README updated" if changed else "README already up to date")
