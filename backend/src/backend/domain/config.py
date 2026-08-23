from pathlib import Path

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


def backend_root() -> Path:
    """Root of the installed ``backend`` package (src/backend)."""
    return Path(__file__).resolve().parents[1]


def project_root() -> Path:
    """Repository root (parent of the ``src`` layout)."""
    return backend_root().parent.parent


class RuntimeSettings(BaseSettings):
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_model_source: str = "modelscope"
    embedding_auto_download: bool = True
    embedding_local_files_only: bool = True
    embedding_device: str = "cpu"
    embedding_dim: int = 384
    max_chunk_tokens: int = 800
    chunk_overlap_tokens: int = 100
    retrieval_top_k: int = 5
    upload_max_bytes: int = 50 * 1024 * 1024
    app_env: str = "development"
    scipal_data_dir: str | None = None
    scipal_model_dir: str | None = None
    scipal_db_path: str | None = None
    mineru_torch_device: str = "cpu"
    mineru_disable_ocr: bool = True
    mineru_table_enable: bool = True
    mineru_formula_enable: bool = True
    mineru_show_download_progress: bool = False
    scipal_eval_output_dir: str = "eval_outputs"
    scipal_eval_document_map_path: str = "docs/eval_document_map.json"
    # Index poll parameters
    index_poll_interval: float = 0.05
    index_poll_max_interval: float = 1.0
    index_max_wait: float = 10.0
    runner_idle_poll_interval: float = 0.05
    # Retrieval parameters
    source_excerpt_max_chars: int = 220
    max_expanded_chunks: int = 8
    same_section_window: int = 1
    adjacent_window: int = 1
    bm25_top_k: int = 8
    dense_top_k: int = 8
    seed_top_k: int = 8
    rrf_k: int = 60
    include_linked_blocks: bool = False
    # Reranker
    reranker_enabled: bool = True
    reranker_model_id: str = "BAAI/bge-reranker-v2-m3"
    reranker_device: str = "cpu"
    reranker_auto_download: bool = True
    reranker_max_length: int = 1024
    rerank_top_k: int = 8
    reranker_remote_enabled: bool = True
    reranker_remote_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_remote_base_url: str = "https://api.siliconflow.cn/v1"
    # MinerU Cloud API
    mineru_api_base_url: str = "https://mineru.net"
    mineru_api_key: str | None = None
    mineru_api_timeout: int = 300
    mineru_api_poll_interval: float = 2.0
    mineru_api_max_poll_time: int = 600
    # Remote Embedding API (SiliconFlow / OpenAI-compatible)
    embedding_remote_api_key: str | None = None
    embedding_remote_model: str = "Qwen/Qwen3-VL-Embedding-8B"
    embedding_remote_base_url: str = "https://api.siliconflow.cn/v1"
    # CORS
    cors_origin_regex: str = r"http://(localhost|127\.0\.0\.1):\d+"
    # Query rewrite enhancement
    history_rewrite_enabled: bool = True
    history_rewrite_max_rounds: int = 4
    history_rewrite_min_query_length: int = 3
    term_expand_enabled: bool = True
    term_expand_glossary_path: str = "backend/data/term_glossary.json"
    term_expand_llm_fallback: bool = True
    # Multi-model fallback
    llm_fallback_enabled: bool = False
    fallback_api_key: str | None = None
    fallback_base_url: str | None = None
    fallback_model: str = "glm-4-flash"
    ollama_base_url: str | None = None
    ollama_model: str = "qwen2.5:7b"
    # Auth
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080
    # User-facing messages
    msg_index_not_ready: str = "论文仍在处理中，请稍后重试。"
    msg_empty_retrieval: str = "未在当前检索结果中找到可支持该问题的论文依据。"
    msg_no_valid_citations: str = "模型生成的回答中未引用有效论文来源，请核实。"
    msg_default_session_title: str = "新论文会话"

    model_config = SettingsConfigDict(env_file=project_root() / ".env", extra="ignore")


class Settings(RuntimeSettings):
    deepseek_api_key: str


settings = RuntimeSettings()


def require_generation_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        raise RuntimeError(
            "DeepSeek generation requires DEEPSEEK_API_KEY to be configured."
        ) from exc


def default_data_dir() -> Path:
    return backend_root() / "data"


def data_dir() -> Path:
    """Get data directory, creating it if needed. Use get_data_dir() for read-only access."""
    configured = settings.scipal_data_dir
    path = Path(configured).expanduser() if configured else default_data_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_data_dir() -> Path:
    """Read-only access to data directory, no mkdir side effect."""
    configured = settings.scipal_data_dir
    return Path(configured).expanduser() if configured else default_data_dir()


def default_model_dir() -> Path:
    return project_root() / "data" / "model_cache"


def model_dir() -> Path:
    configured = settings.scipal_model_dir
    path = Path(configured).expanduser() if configured else default_model_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def mineru_model_dir() -> Path:
    path = model_dir() / "mineru"
    path.mkdir(parents=True, exist_ok=True)
    return path


def mineru_modelscope_cache_dir() -> Path:
    path = mineru_model_dir() / "modelscope"
    path.mkdir(parents=True, exist_ok=True)
    return path


def embedding_model_dir() -> Path:
    return model_dir() / "embeddings" / settings.embedding_model.rsplit("/", 1)[-1]
