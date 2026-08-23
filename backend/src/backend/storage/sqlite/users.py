import uuid
from datetime import UTC, datetime

from backend.storage.sqlite.connection import connect, transaction


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def create_user(username: str, hashed_password: str) -> dict:
    user_id = str(uuid.uuid4())
    timestamp = _now_iso()
    with transaction() as conn:
        conn.execute(
            "INSERT INTO users (id, username, hashed_password, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, username, hashed_password, timestamp, timestamp),
        )
    user = get_user_by_id(user_id)
    if user is None:
        raise RuntimeError("创建用户失败")
    return user


def get_user_by_username(username: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None
