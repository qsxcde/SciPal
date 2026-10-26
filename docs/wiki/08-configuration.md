# 08 配置参考

定义：`backend/src/backend/config.py`（`RuntimeSettings`，pydantic-settings `BaseSettings`）
加载：`SettingsConfigDict(env_file=env_file_path(), extra="ignore")`，其中
`env_file_path() = backend_project_dir() / ".env"`
即：读取 **`backend/.env`**，未设置 `env_prefix`，环境变量名 = 字段名大写。
仓库根目录的 `.env` **不会被读取**，启动时会打印一条 warning。

```
SciPal/backend/.env  ← 后端配置（唯一生效路径）
SciPal/frontend/.env ← 仅 VITE_* 变量
```

启动日志会打印实际加载的路径：
`Configuration: loading /…/SciPal/backend/.env`。

模块级单例 `settings = RuntimeSettings()` 在 import 时即完成加载；改配置必须重启进程。

## 1. 必填与校验

- `RuntimeSettings` 的 `deepseek_api_key` 为 `None`，**启动时不校验**。
- 真正需要生成时才调用 `require_generation_settings()`（`generation/llm.py` 首次取客户端时），缺失 `DEEPSEEK_API_KEY` 抛 `RuntimeError("DeepSeek generation requires DEEPSEEK_API_KEY to be configured.")`。
- 因此：可以只做上传/检索；一旦发起对话且缺 key，SSE 会返回 `error` 事件。

## 2. 全部配置项

### 2.1 LLM 生成

| 变量 | 默认 | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | `None` | 主模型密钥；对话必需 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | OpenAI 兼容端点 |
| `DEEPSEEK_MODEL` | `deepseek-v4-flash` | 主模型名 |

### 2.2 多模型降级

| 变量 | 默认 | 说明 |
|---|---|---|
| `LLM_FALLBACK_ENABLED` | `False` | 总开关，同时控制 fallback 与 ollama |
| `FALLBACK_API_KEY` | `None` | 备用 provider 密钥 |
| `FALLBACK_BASE_URL` | `None` | 为空则不启用备用 provider |
| `FALLBACK_MODEL` | `glm-4-flash` | |
| `OLLAMA_BASE_URL` | `None` | 为空则不启用 Ollama |
| `OLLAMA_MODEL` | `qwen2.5:7b` | |

### 2.3 Embedding

| 变量 | 默认 | 说明 |
|---|---|---|
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | 本地模型仓库 ID |
| `EMBEDDING_MODEL_SOURCE` | `modelscope` | `modelscope` 或 `huggingface` |
| `EMBEDDING_AUTO_DOWNLOAD` | `True` | 本地无权重时是否下载 |
| `EMBEDDING_LOCAL_FILES_ONLY` | `True` | 传给 SentenceTransformer |
| `EMBEDDING_DEVICE` | `cpu` | `cpu` / `cuda` / `mps` |
| `EMBEDDING_DIM` | `384` | **决定 FAISS 索引维度**，换模型必须同步 |
| `EMBEDDING_REMOTE_API_KEY` | `None` | 配置后远程优先 |
| `EMBEDDING_REMOTE_MODEL` | `Qwen/Qwen3-VL-Embedding-8B` | |
| `EMBEDDING_REMOTE_BASE_URL` | `https://api.siliconflow.cn/v1` | |

### 2.4 分块与上传

| 变量 | 默认 | 说明 |
|---|---|---|
| `MAX_CHUNK_TOKENS` | `800` | 估算 token 上限（非真实 tokenizer） |
| `CHUNK_OVERLAP_TOKENS` | `100` | 重叠按**字符**截取 |
| `UPLOAD_MAX_BYTES` | `52428800` | 50 MiB |

### 2.5 存储路径

| 变量 | 默认 | 说明 |
|---|---|---|
| `SCIPAL_DATA_DIR` | `None` → `backend/data` | 运行时数据根 |
| `SCIPAL_MODEL_DIR` | `None` → `<数据根>/model_cache` | 模型缓存根 |
| `SCIPAL_DB_PATH` | `None` → `<数据根>/scipal.db` → `backend/src/backend/storage/sqlite/scipal.db` | SQLite 文件 |

### 2.6 MinerU

| 变量 | 默认 | 说明 |
|---|---|---|
| `MINERU_API_KEY` | `None` | 配置后启用云解析（优先级最高） |
| `MINERU_API_BASE_URL` | `https://mineru.net` | |
| `MINERU_API_TIMEOUT` | `300` | 秒 |
| `MINERU_API_POLL_INTERVAL` | `2.0` | 秒 |
| `MINERU_API_MAX_POLL_TIME` | `600` | 秒 |
| `MINERU_TORCH_DEVICE` | `cpu` | 本地 CLI 设备 |
| `MINERU_DISABLE_OCR` | `True` | |
| `MINERU_TABLE_ENABLE` | `True` | |
| `MINERU_FORMULA_ENABLE` | `True` | |
| `MINERU_SHOW_DOWNLOAD_PROGRESS` | `False` | |

### 2.7 索引与任务轮询

| 变量 | 默认 | 说明 |
|---|---|---|
| `INDEX_POLL_INTERVAL` | `0.05` | 对话等待索引的初始间隔 |
| `INDEX_POLL_MAX_INTERVAL` | `1.0` | 退避上限 |
| `INDEX_MAX_WAIT` | `10.0` | 总等待预算（秒） |
| `RUNNER_IDLE_POLL_INTERVAL` | `0.05` | runner 空转间隔 |

### 2.8 检索

| 变量 | 默认 | 说明 |
|---|---|---|
| `RETRIEVAL_TOP_K` | `5` | 仅纯 dense 分支使用 |
| `SOURCE_EXCERPT_MAX_CHARS` | `220` | `SourceRef.text_excerpt` 截断长度 |
| `MAX_EXPANDED_CHUNKS` | `8` | 上下文块数上限 |
| `SAME_SECTION_WINDOW` | `1` | 同章节邻居窗口 |
| `ADJACENT_WINDOW` | `1` | 相邻 chunk 窗口 |
| `BM25_TOP_K` | `8` | |
| `DENSE_TOP_K` | `8` | 设 0 即关闭 dense |
| `SEED_TOP_K` | `8` | RRF 后保留数 |
| `RRF_K` | `60` | |
| `INCLUDE_LINKED_BLOCKS` | `False` | 是否带入 caption 关联块 |

### 2.9 Reranker

| 变量 | 默认 | 说明 |
|---|---|---|
| `RERANKER_ENABLED` | `True` | 关掉即跳过重排 |
| `RERANKER_MODEL_ID` | `BAAI/bge-reranker-v2-m3` | 本地模型 |
| `RERANKER_DEVICE` | `cpu` | |
| `RERANKER_AUTO_DOWNLOAD` | `True` | |
| `RERANKER_MAX_LENGTH` | `1024` | |
| `RERANK_TOP_K` | `8` | |
| `RERANKER_REMOTE_ENABLED` | `True` | 需同时配置 `EMBEDDING_REMOTE_API_KEY` |
| `RERANKER_REMOTE_MODEL` | `BAAI/bge-reranker-v2-m3` | |
| `RERANKER_REMOTE_BASE_URL` | `https://api.siliconflow.cn/v1` | |

### 2.10 查询改写与术语扩展

| 变量 | 默认 | 说明 |
|---|---|---|
| `HISTORY_REWRITE_ENABLED` | `True` | |
| `HISTORY_REWRITE_MAX_ROUNDS` | `4` | 参与改写的最近轮数 |
| `HISTORY_REWRITE_MIN_QUERY_LENGTH` | `3` | 短查询强制改写 |
| `TERM_EXPAND_ENABLED` | `True` | |
| `TERM_EXPAND_GLOSSARY_PATH` | `backend/data/term_glossary.json` | **相对当前工作目录** |
| `TERM_EXPAND_LLM_FALLBACK` | `True` | 词表未命中时调 LLM |

### 2.11 鉴权

| 变量 | 默认 | 说明 |
|---|---|---|
| `JWT_SECRET_KEY` | `""` | 为空且 `APP_ENV` 为开发类取值 = 匿名旁路（数据接口免鉴权、auth 接口 400）；生产环境必须设置 |
| `JWT_ALGORITHM` | `HS256` | |
| `JWT_EXPIRE_MINUTES` | `10080` | 7 天 |

### 2.12 应用与文案

| 变量 | 默认 | 说明 |
|---|---|---|
| `APP_ENV` | `development` | 决定是否允许匿名旁路：`development/dev/local/test/testing` 允许；其它值（如 `production`）在缺 `JWT_SECRET_KEY` 时对数据接口返回 503 |
| `CORS_ORIGIN_REGEX` | `http://(localhost\|127\.0\.0\.1):\d+` | 前端跨域 |
| `MSG_INDEX_NOT_READY` | `论文仍在处理中，请稍后重试。` | 索引超时提示 |
| `MSG_EMPTY_RETRIEVAL` | `未在当前检索结果中找到可支持该问题的论文依据。` | 检索为空提示 |
| `MSG_NO_VALID_CITATIONS` | `模型生成的回答中未引用有效论文来源，请核实。` | 引用校验 warning |
| `MSG_DEFAULT_SESSION_TITLE` | `新论文会话` | 默认标题，同时是"是否自动改名"的哨兵值 |

## 3. 路径解析

```
backend_root()  = backend/src/backend
project_root()  = 仓库根（.env 位置）

data_dir()      = SCIPAL_DATA_DIR or backend_root().parent / "data"   → backend/data
model_dir()     = SCIPAL_MODEL_DIR or data_dir()/model_cache
mineru_model_dir()           = model_dir()/mineru
mineru_modelscope_cache_dir()= model_dir()/mineru/modelscope
embedding_model_dir()        = model_dir()/embeddings/<EMBEDDING_MODEL 末段名>

DB: SCIPAL_DB_PATH → data_dir()/scipal.db → backend/src/backend/storage/sqlite/scipal.db
```

三者都会 `mkdir(parents=True, exist_ok=True)`，目录不存在会自动创建。

## 4. 示例 `.env`

```env
# 必填：对话生成
DEEPSEEK_API_KEY=sk-xxxx
DEEPSEEK_MODEL=deepseek-v4-flash

# 可选：远程 embedding（配置后优先于本地）
# EMBEDDING_REMOTE_API_KEY=sk-yyyy
# EMBEDDING_REMOTE_MODEL=Qwen/Qwen3-VL-Embedding-8B

# 本地 embedding
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
EMBEDDING_MODEL_SOURCE=modelscope
EMBEDDING_DEVICE=cpu
EMBEDDING_DIM=384

# 解析
MINERU_TORCH_DEVICE=cpu
MINERU_DISABLE_OCR=true

# 存储
# SCIPAL_DATA_DIR=/var/lib/scipal
# SCIPAL_DB_PATH=/var/lib/scipal/scipal.db

# 鉴权（留空 = 开发旁路）
# JWT_SECRET_KEY=change-me

# 多模型降级
# LLM_FALLBACK_ENABLED=true
# FALLBACK_API_KEY=sk-zzzz
# FALLBACK_BASE_URL=https://open.bigmodel.cn/api/paas/v4
# FALLBACK_MODEL=glm-4-flash
```

## 5. 改配置时的注意事项

1. **`EMBEDDING_DIM` 必须与模型输出维度一致**，否则追加索引时抛 `ValueError("Embedding dimension mismatch")`；换模型后需对已有文档重建索引。
2. **切换 embedding 空间等于让旧索引失效**，历史会话的 FAISS 快照仍指向旧向量空间，检索结果不可比。
3. `TERM_EXPAND_GLOSSARY_PATH` 是相对路径，按进程工作目录解析；用 `uv run --project backend ...` 时工作目录是仓库根，因此默认可命中 `backend/data/term_glossary.json`。
4. 生产必须显式设置 `SCIPAL_DB_PATH` 或 `SCIPAL_DATA_DIR`，否则默认 DB 会落进源码包目录。
5. 生产必须设置 `JWT_SECRET_KEY`，否则任何人可匿名读写全部会话（且归属校验缺失）。
