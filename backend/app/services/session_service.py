from backend.rag.indexing.vector_store import AbstractVectorStore
from backend.domain.exceptions import SessionNotFoundError
from backend.storage.sqlite import sessions
from backend.storage.vector_db import registry as index_registry
from backend.storage.paths import remove_session_dir

def create_session() -> str:
    session = sessions.create_session()
    return session["id"]

def get_store(session_id: str) -> AbstractVectorStore:
    session = sessions.get_session(session_id)
    if session is None or session["is_archived"]:
        raise SessionNotFoundError(f"Session not found: {session_id}")
    return index_registry.get_store(session_id)

def destroy_session(session_id: str) -> None:
    sessions.archive_session(session_id)
    index_registry.discard_store(session_id)
    remove_session_dir(session_id)
