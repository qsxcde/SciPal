from backend.storage.sqlite.connection import connect

CURRENT_SCHEMA_VERSION = 1

_in_progress = False


def init_db() -> None:
    """每次 connect() 调用时执行；user_version 检查确保对已存在的 DB 零开销，对新 DB 文件（测试隔离）也能正确初始化。"""
    global _in_progress
    if _in_progress:
        return
    _in_progress = True
    try:
        conn = connect()
        try:
            if conn.execute("PRAGMA user_version").fetchone()[0] < CURRENT_SCHEMA_VERSION:
                _create_initial_schema(conn)
                conn.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    finally:
        _in_progress = False


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
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_session_id ON documents(session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_session_id ON chunks(session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_session_status ON jobs(session_id, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_index_snapshots_session_status ON index_snapshots(session_id, status)")
