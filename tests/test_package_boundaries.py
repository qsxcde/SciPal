"""Architectural boundaries: layers may only depend downwards.

These checks are static (AST only) so they stay fast and do not require
torch / faiss / mineru to be installed.
"""

import ast
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend" / "src" / "backend"

# 已知违反：RAG 能力层仍在模块作用域读取全局 settings（配置未注入）。
# 这是棘轮清单：新增违规会让测试失败，修掉后可以直接删掉对应条目。
RAG_SETTINGS_DEBT = {
    "rag/embedding/__init__.py",
    "rag/embedding/remote_embedder.py",
    "rag/generation/llm.py",
    "rag/generation/model_client.py",
    "rag/ingestion/mineru_api_backend.py",
    "rag/ingestion/mineru_backend.py",
    "rag/ingestion/pipeline.py",
    "rag/ingestion/text_pdf_backend.py",
    "rag/retrieval/remote_reranker.py",
    "rag/retrieval/reranker.py",
    "rag/retrieval/retriever.py",
}

# worker/runner.py 是作业队列的适配器，直接操作 jobs 表属预期；
# 处理器（handlers）必须只调用用例。
WORKER_STORAGE_EXEMPT = {"worker/runner.py"}


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


def _rel(path: Path) -> str:
    return str(path.relative_to(BACKEND_ROOT)).replace("\\", "/")


def _violations(
    package: str, forbidden_prefix: str, exempt: set[str] | None = None
) -> list[str]:
    exempt = exempt or set()
    offenders = []
    for path in _modules_under(package):
        if _rel(path) in exempt:
            continue
        for module in _imported_modules(path):
            if module == forbidden_prefix or module.startswith(f"{forbidden_prefix}."):
                offenders.append(f"{_rel(path)} -> {module}")
    return offenders


def _assert_never_imports(package: str, forbidden_prefix: str, exempt: set[str] | None = None) -> None:
    offenders = _violations(package, forbidden_prefix, exempt)
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
def test_api_layer_does_not_touch_persistence():
    _assert_never_imports("api", "backend.storage")


@pytest.mark.unit
def test_worker_handlers_do_not_touch_persistence():
    _assert_never_imports("worker", "backend.storage", exempt=WORKER_STORAGE_EXEMPT)


@pytest.mark.unit
def test_only_api_layer_and_composition_root_import_fastapi():
    allowed = ("api/", "main.py")
    offenders = [
        _rel(path)
        for path in BACKEND_ROOT.rglob("*.py")
        if not _rel(path).startswith(allowed)
        for module in _imported_modules(path)
        if module == "fastapi" or module.startswith("fastapi.")
    ]
    assert offenders == [], f"only api/ and main.py may import fastapi: {offenders}"


@pytest.mark.unit
def test_rag_layer_reads_settings_only_where_documented():
    """Capability modules should receive configuration, not read it globally.

    Ratchet: the allowlist may shrink but never grow. Every entry left here is
    a module that cannot be configured per call and cannot be unit tested
    without touching the global settings singleton.
    """
    offenders = {
        _rel(path)
        for path in _modules_under("rag")
        for module in _imported_modules(path)
        if module == "backend.config" or module.startswith("backend.config.")
    }

    new_offenders = sorted(offenders - RAG_SETTINGS_DEBT)
    assert new_offenders == [], f"new rag modules must not read global settings: {new_offenders}"
    assert len(offenders) <= len(RAG_SETTINGS_DEBT)
