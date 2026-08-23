import threading

from backend.storage.sqlite.connection import connect

CURRENT_SCHEMA_VERSION = 5

_init_lock = threading.RLock()


def init_db() -> None:
    """Thread-safe schema initialization and migration."""
    with _init_lock:
        conn = connect()
        try:
            current_version = conn.execute("PRAGMA user_version").fetchone()[0]
            if current_version < 1:
                _create_initial_schema(conn)
                current_version = 1
            if current_version < CURRENT_SCHEMA_VERSION:
                _migrate_schema(conn, current_version)
                conn.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _migrate_schema(conn, from_version: int) -> None:
    """Run incremental schema migrations."""
    if from_version < 2:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_chunks_unique_document_chunk "
            "ON chunks(document_id, chunk_index)"
        )
    if from_version < 3:
        conn.execute("ALTER TABLE retrieval_indexes ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")
        conn.execute("UPDATE retrieval_indexes SET created_at = updated_at WHERE created_at = ''")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_list "
            "ON sessions(is_archived, is_pinned, updated_at DESC) WHERE is_archived = 0"
        )
    if from_version < 4:
        _migrate_add_cascade_delete(conn)
    if from_version < 5:
        _migrate_add_users_table(conn)


def _migrate_add_users_table(conn) -> None:
    """Add users table for JWT auth (v5)."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            hashed_password TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)


def _migrate_add_cascade_delete(conn) -> None:
    """Recreate FK-bearing tables with ON DELETE CASCADE (v4)."""
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.executescript("""
        CREATE TABLE documents_new (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
          filename TEXT NOT NULL,
          file_path TEXT NOT NULL,
          mime_type TEXT NOT NULL,
          file_size INTEGER NOT NULL,
          chunk_count INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL,
          error_message TEXT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          parsed_ir_path TEXT NULL,
          parsed_markdown_path TEXT NULL,
          quality_report_path TEXT NULL,
          parser_name TEXT NULL,
          parser_version TEXT NULL,
          parse_quality_status TEXT NULL
        );
        INSERT INTO documents_new SELECT * FROM documents;
        DROP TABLE documents;
        ALTER TABLE documents_new RENAME TO documents;

        CREATE TABLE messages_new (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
          role TEXT NOT NULL,
          content TEXT NOT NULL,
          sources_json TEXT NULL,
          status TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        INSERT INTO messages_new SELECT * FROM messages;
        DROP TABLE messages;
        ALTER TABLE messages_new RENAME TO messages;

        CREATE TABLE chunks_new (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
          document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
          section TEXT NOT NULL,
          chunk_index INTEGER NOT NULL,
          text_excerpt TEXT NOT NULL,
          text_content TEXT NOT NULL,
          type TEXT NOT NULL,
          created_at TEXT NOT NULL,
          section_path_json TEXT NULL,
          page_start INTEGER NULL,
          page_end INTEGER NULL,
          bbox_json TEXT NULL,
          block_ids_json TEXT NULL,
          block_types_json TEXT NULL,
          linked_block_ids_json TEXT NULL,
          confidence REAL NULL
        );
        INSERT INTO chunks_new SELECT * FROM chunks;
        DROP TABLE chunks;
        ALTER TABLE chunks_new RENAME TO chunks;

        CREATE TABLE retrieval_indexes_new (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
          index_path TEXT NOT NULL,
          chunks_path TEXT NOT NULL,
          status TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        INSERT INTO retrieval_indexes_new SELECT * FROM retrieval_indexes;
        DROP TABLE retrieval_indexes;
        ALTER TABLE retrieval_indexes_new RENAME TO retrieval_indexes;

        CREATE TABLE jobs_new (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
          document_id TEXT NULL REFERENCES documents(id) ON DELETE SET NULL,
          type TEXT NOT NULL,
          status TEXT NOT NULL,
          stage TEXT NOT NULL,
          attempt INTEGER NOT NULL DEFAULT 0,
          error_message TEXT NULL,
          payload_json TEXT NULL,
          created_at TEXT NOT NULL,
          started_at TEXT NULL,
          finished_at TEXT NULL
        );
        INSERT INTO jobs_new SELECT * FROM jobs;
        DROP TABLE jobs;
        ALTER TABLE jobs_new RENAME TO jobs;

        CREATE TABLE index_snapshots_new (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
          status TEXT NOT NULL,
          index_path TEXT NOT NULL,
          chunks_path TEXT NOT NULL,
          document_ids_json TEXT NOT NULL,
          error_message TEXT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        INSERT INTO index_snapshots_new SELECT * FROM index_snapshots;
        DROP TABLE index_snapshots;
        ALTER TABLE index_snapshots_new RENAME TO index_snapshots;
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_session_id ON documents(session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_session_id ON chunks(session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_chunks_unique_document_chunk ON chunks(document_id, chunk_index)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_session_status ON jobs(session_id, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_index_snapshots_session_status ON index_snapshots(session_id, status)")
    conn.execute("PRAGMA foreign_keys = ON")


def _create_initial_schema(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sessions (
          id TEXT PRIMARY KEY,
          title TEXT NOT NULL,
          user_id TEXT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          last_opened_at TEXT NOT NULL,
          is_archived INTEGER NOT NULL DEFAULT 0,
          is_pinned INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS documents (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL REFERENCES sessions(id),
          filename TEXT NOT NULL,
          file_path TEXT NOT NULL,
          mime_type TEXT NOT NULL,
          file_size INTEGER NOT NULL,
          chunk_count INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL,
          error_message TEXT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          parsed_ir_path TEXT NULL,
          parsed_markdown_path TEXT NULL,
          quality_report_path TEXT NULL,
          parser_name TEXT NULL,
          parser_version TEXT NULL,
          parse_quality_status TEXT NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL REFERENCES sessions(id),
          role TEXT NOT NULL,
          content TEXT NOT NULL,
          sources_json TEXT NULL,
          status TEXT NOT NULL,
          created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS chunks (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL REFERENCES sessions(id),
          document_id TEXT NOT NULL REFERENCES documents(id),
          section TEXT NOT NULL,
          chunk_index INTEGER NOT NULL,
          text_excerpt TEXT NOT NULL,
          text_content TEXT NOT NULL,
          type TEXT NOT NULL,
          created_at TEXT NOT NULL,
          section_path_json TEXT NULL,
          page_start INTEGER NULL,
          page_end INTEGER NULL,
          bbox_json TEXT NULL,
          block_ids_json TEXT NULL,
          block_types_json TEXT NULL,
          linked_block_ids_json TEXT NULL,
          confidence REAL NULL
        );

        CREATE TABLE IF NOT EXISTS retrieval_indexes (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL REFERENCES sessions(id),
          index_path TEXT NOT NULL,
          chunks_path TEXT NOT NULL,
          status TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL REFERENCES sessions(id),
          document_id TEXT NULL REFERENCES documents(id),
          type TEXT NOT NULL,
          status TEXT NOT NULL,
          stage TEXT NOT NULL,
          attempt INTEGER NOT NULL DEFAULT 0,
          error_message TEXT NULL,
          payload_json TEXT NULL,
          created_at TEXT NOT NULL,
          started_at TEXT NULL,
          finished_at TEXT NULL
        );

        CREATE TABLE IF NOT EXISTS index_snapshots (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL REFERENCES sessions(id),
          status TEXT NOT NULL,
          index_path TEXT NOT NULL,
          chunks_path TEXT NOT NULL,
          document_ids_json TEXT NOT NULL,
          error_message TEXT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            hashed_password TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_session_id ON documents(session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_session_id ON chunks(session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_chunks_unique_document_chunk ON chunks(document_id, chunk_index)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_session_status ON jobs(session_id, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_index_snapshots_session_status ON index_snapshots(session_id, status)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_list "
        "ON sessions(is_archived, is_pinned, updated_at DESC) WHERE is_archived = 0"
    )
