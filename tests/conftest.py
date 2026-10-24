"""Shared fixtures: every test gets its own SQLite file and data directory."""

import pytest

from backend.domain import config
from backend.storage.sqlite.schema import init_db


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    """Point settings at throwaway paths and create a fresh schema."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    monkeypatch.setattr(config.settings, "scipal_db_path", str(tmp_path / "scipal.db"))
    monkeypatch.setattr(config.settings, "scipal_data_dir", str(data_root))
    init_db()
    return tmp_path
