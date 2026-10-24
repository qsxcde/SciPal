"""Authorization: session ownership and the anonymous development bypass."""

import pytest
from fastapi import HTTPException

from backend.app import security
from backend.domain import config
from backend.domain.access import session_is_accessible


@pytest.mark.unit
def test_legacy_session_without_owner_stays_readable():
    assert session_is_accessible({"user_id": None, "is_archived": 0}, "user-a") is True
    assert session_is_accessible({"user_id": None, "is_archived": 0}, None) is True


@pytest.mark.unit
def test_owner_can_access_own_session():
    assert session_is_accessible({"user_id": "user-a", "is_archived": 0}, "user-a") is True


@pytest.mark.unit
def test_other_or_anonymous_caller_is_rejected():
    session = {"user_id": "user-a", "is_archived": 0}

    assert session_is_accessible(session, "user-b") is False
    assert session_is_accessible(session, None) is False


@pytest.mark.unit
def test_archived_or_missing_session_is_rejected():
    assert session_is_accessible(None, "user-a") is False
    assert session_is_accessible({"user_id": "user-a", "is_archived": 1}, "user-a") is False


@pytest.mark.unit
async def test_development_bypass_returns_local_user(monkeypatch):
    monkeypatch.setattr(config.settings, "jwt_secret_key", "")
    monkeypatch.setattr(config.settings, "app_env", "development")

    user = await security.get_current_user(token=None)

    assert user == {"id": "", "username": "dev"}


@pytest.mark.unit
async def test_production_without_secret_fails_closed(monkeypatch):
    monkeypatch.setattr(config.settings, "jwt_secret_key", "")
    monkeypatch.setattr(config.settings, "app_env", "production")

    with pytest.raises(HTTPException) as exc_info:
        await security.get_current_user(token=None)

    assert exc_info.value.status_code == 503
