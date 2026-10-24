"""Architectural boundaries: layers may only depend downwards.

These checks are static (AST only) so they stay fast and do not require
torch / faiss / mineru to be installed.
"""

import ast
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend" / "src" / "backend"


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                modules.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
    return modules


def _modules_under(package: str) -> list[Path]:
    return sorted((BACKEND_ROOT / package).rglob("*.py"))


def _assert_never_imports(package: str, forbidden_prefix: str) -> None:
    offenders = []
    for path in _modules_under(package):
        for module in _imported_modules(path):
            if module == forbidden_prefix or module.startswith(f"{forbidden_prefix}."):
                offenders.append(f"{path.relative_to(BACKEND_ROOT)} -> {module}")
    assert offenders == [], f"{package}/ must not import {forbidden_prefix}: {offenders}"


@pytest.mark.unit
def test_application_layer_does_not_depend_on_web_framework():
    _assert_never_imports("application", "fastapi")


@pytest.mark.unit
def test_storage_layer_does_not_depend_on_rag_capabilities():
    _assert_never_imports("storage", "backend.rag")


@pytest.mark.unit
def test_domain_layer_depends_on_nothing_above_it():
    for forbidden in ("backend.api", "backend.application", "backend.rag", "backend.storage"):
        _assert_never_imports("domain", forbidden)


@pytest.mark.unit
def test_rag_capability_layers_do_not_read_global_settings():
    """Capability modules receive configuration as arguments."""
    assert "backend.config" not in _imported_modules(BACKEND_ROOT / "rag" / "answer.py")


@pytest.mark.unit
def test_worker_does_not_depend_on_http_layer():
    _assert_never_imports("worker", "backend.api")


@pytest.mark.unit
def test_only_api_layer_and_composition_root_import_fastapi():
    allowed = ("api/", "main.py")
    offenders = [
        str(path.relative_to(BACKEND_ROOT))
        for path in BACKEND_ROOT.rglob("*.py")
        if not str(path.relative_to(BACKEND_ROOT)).startswith(allowed)
        for module in _imported_modules(path)
        if module == "fastapi" or module.startswith("fastapi.")
    ]
    assert offenders == [], f"only api/ and main.py may import fastapi: {offenders}"
