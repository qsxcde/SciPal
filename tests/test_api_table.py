"""README endpoint table must match the committed contract."""

import json

import pytest

from backend.scripts.api_table import END, START, openapi_path, readme_path, render_block


@pytest.mark.unit
def test_readme_endpoint_table_matches_openapi():
    schema = json.loads(openapi_path().read_text(encoding="utf-8"))
    readme = readme_path().read_text(encoding="utf-8")

    expected = render_block(schema)
    actual = readme[readme.index(START) : readme.index(END) + len(END)]

    assert actual == expected, (
        "README 的端点表已过期：运行 "
        "uv run --project backend python -m backend.scripts.api_table"
    )
