import json
import uuid
from typing import Literal

from backend.rag.ingestion.metadata import SourceRef
from backend.storage.sqlite.connection import connect, transaction
from backend.storage.sqlite.schema import init_db
from backend.storage.sqlite.sessions import now_iso, touch_session


def _encode_sources(sources: list[SourceRef] | None) -> str | None:
    if sources is None:
        return None
    return json.dumps([source.model_dump() for source in sources], ensure_ascii=False)


def _decode_sources(value: str | None) -> list[dict]:
    if not value:
        return []
    parsed = json.loads(value)
    return parsed if isinstance(parsed, list) else []


def create_message(
    session_id: str,
    role: Literal["user", "assistant"],
    content: str,
    sources: list[SourceRef] | None = None,
    status: Literal["complete", "failed"] = "complete",
) -> dict:
    init_db()
    message_id = str(uuid.uuid4())
    timestamp = now_iso()
    sources_json = _encode_sources(sources)
    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO messages (id, session_id, role, content, sources_json, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (message_id, session_id, role, content, sources_json, status, timestamp),
        )
    touch_session(session_id)
    message = get_message(message_id)
    if message is None:
        raise RuntimeError("创建消息失败")
    return message


def get_message(message_id: str) -> dict | None:
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
    if not row:
        return None
    message = dict(row)
    message["sources"] = _decode_sources(message.pop("sources_json"))
    return message


def list_messages(session_id: str) -> list[dict]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
    result = []
    for row in rows:
        message = dict(row)
        message["sources"] = _decode_sources(message.pop("sources_json"))
        result.append(message)
    return result
