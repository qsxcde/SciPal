"""Deployment contract for the .env file.

The docs, the startup warning and pydantic-settings must all point at the same
file; a mismatch silently disables configuration (and therefore auth).
"""

import pytest

from backend import config


@pytest.mark.unit
def test_settings_load_dotenv_from_backend_directory():
    assert config.env_file_path() == config.backend_project_dir() / ".env"
    assert config.env_file_path().parent.name == "backend"
    assert config.RuntimeSettings.model_config["env_file"] == config.env_file_path()


@pytest.mark.unit
def test_repo_root_env_file_is_reported_as_ignored(tmp_path, monkeypatch):
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=sk-stray\n", encoding="utf-8")
    monkeypatch.setattr(config, "backend_project_dir", lambda: backend_dir)

    warning = config.repo_env_file_warning()

    assert warning is not None
    assert "backend" in warning
