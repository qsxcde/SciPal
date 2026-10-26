"""Startup self-check: never serve traffic with authentication silently disabled."""

import pytest

pytest.importorskip("torch", reason="backend.main imports the RAG stack")
pytest.importorskip("faiss", reason="faiss-cpu is not installed")

from backend import config
from backend.main import _validate_runtime_config


@pytest.mark.unit
def test_production_without_jwt_secret_refuses_to_start(monkeypatch):
    monkeypatch.setattr(config.settings, "jwt_secret_key", "")
    monkeypatch.setattr(config.settings, "app_env", "production")

    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        _validate_runtime_config()


@pytest.mark.unit
def test_development_without_jwt_secret_warns_but_starts(monkeypatch, caplog):
    monkeypatch.setattr(config.settings, "jwt_secret_key", "")
    monkeypatch.setattr(config.settings, "app_env", "development")

    with caplog.at_level("WARNING"):
        _validate_runtime_config()

    assert "anonymous access enabled" in caplog.text


@pytest.mark.unit
def test_configured_secret_passes_in_any_environment(monkeypatch):
    monkeypatch.setattr(config.settings, "jwt_secret_key", "secret-value")
    monkeypatch.setattr(config.settings, "app_env", "production")

    _validate_runtime_config()
