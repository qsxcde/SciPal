"""The committed OpenAPI file must match the running app."""

import json

import pytest

pytest.importorskip("torch", reason="the API imports the RAG stack")
pytest.importorskip("faiss", reason="faiss-cpu is not installed")

from backend.scripts.export_openapi import build_schema, contracts_dir


@pytest.mark.integration
def test_committed_openapi_matches_the_app():
    committed = json.loads((contracts_dir() / "openapi.json").read_text(encoding="utf-8"))

    assert build_schema() == committed, (
        "contracts/openapi.json is stale: run "
        "uv run --project backend python -m backend.scripts.export_openapi"
    )
