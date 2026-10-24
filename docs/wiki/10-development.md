# 10 开发与运维

## 1. 环境搭建

依赖管理用 [uv](https://github.com/astral-sh/uv)，后端配置在 `backend/pyproject.toml`（包名 `scipal-backend`，`requires-python >= 3.11`）。

```bash
# 1. 配置（仓库根目录，不是 backend/）
cp backend/.env.example .env          # 若 example 不存在则手工创建，字段见 08 章

# 2. 安装（--project 指向 backend，自动创建 backend/.venv）
uv sync --project backend --extra dev --group eval

# 3. 启动后端
uv run --project backend uvicorn backend.app.main:app --reload

# 4. 启动前端（另一个终端）
cd frontend && npm install && npm run dev
```

访问：前端 `http://localhost:5173`，OpenAPI `http://127.0.0.1:8000/docs`，健康检查 `http://127.0.0.1:8000/health`。

依赖分组：

| 分组 | 声明位置 | 内容 |
|---|---|---|
| 运行时 | `[project].dependencies` | fastapi, uvicorn, pydantic, pydantic-settings, python-multipart, python-jose, bcrypt, httpx, numpy, transformers, torch, sentence-transformers, faiss-cpu, mineru, pypdf, modelscope |
| `dev` | `[project.optional-dependencies].dev` | pytest, pytest-asyncio, pytest-cov, pytest-mock |
| `eval` | `[dependency-groups].eval` | langchain-openai, pandas, pyyaml, ragas |

`eval` 是 dependency-group，**必须** `--group eval`；漏加会导致 `scipal_eval` 导入 `langchain_openai` 失败。

控制台入口：`scipal-backend = backend.app.main:main`、`scipal-eval = scipal_eval.cli:main`。

## 2. 测试

### 2.1 现状

- 仓库中**没有任何 `test_*.py` / `*_test.py`**。
- 根 `.gitignore` 忽略 `tests/`，因此测试目录即使存在也不入库。
- `README.md` 列出了 8 个"计划纳入"的 focused suite 文件名，补测时沿用：

```
tests/test_backend_state_models.py
tests/test_document_intake_flow.py
tests/test_index_commit_flow.py
tests/test_chat_waiting_flow.py
tests/test_job_recovery.py
tests/test_backend_state_transitions.py
tests/test_vector_store.py
tests/test_chat_service.py
```

### 2.2 约定

`pytest.ini`（仓库根）：

| 标记 | 语义 |
|---|---|
| `unit` | 不跨进程 / 存储 / API / 服务边界 |
| `integration` | 跨模块、服务、存储或 API 边界 |
| `import_isolation` | 验证导入副作用与导入期依赖边界 |
| `slow` | 慢测试 |

`backend/pyproject.toml` 的 `[tool.pytest.ini_options]`：`asyncio_mode = "auto"`（async 测试无需 `@pytest.mark.asyncio`）、`addopts = "-q"`。

```bash
uv run --project backend pytest -m unit -v
uv run --project backend pytest -m integration -v
```

### 2.3 补测时的入手点

| 主题 | 建议方式 |
|---|---|
| `FAISSVectorStore` | 临时目录 + monkeypatch `_default_embed`，避免加载真实模型 |
| 状态流转 | 直接调仓储函数，断言 CAS 行为（重复 `mark_job_running` 应失败） |
| 快照提交/回滚 | 构造两条快照，模拟 `mark_snapshot_ready` 后抛错，断言 `stale → ready` 恢复 |
| SSE 协议 | 用 `_SSEStreamState` 或假生成器驱动 `consume_stream`，覆盖 token/dict 混用报错 |
| 上传 | 直接调 `intake_document_upload`，覆盖 400/413/404 分支 |

## 3. 代码约定

### 3.1 分层

- 路由层只做参数绑定、状态码、异常转 `HTTPException`；业务编排放 `app/services/`。
- 服务层是**模块级函数**，不定义类，不通过 `Depends` 注入；路由直接 `from ... import service` 调用。
- 仓储层只写 SQL，不写业务判断；返回 `dict`（`sqlite3.Row` 转换）。
- `rag/*` 不依赖 `app/*`，保持可被 CLI/测试直接调用。

### 3.2 数据库

- 所有写操作走 `with transaction() as conn:`，自动 commit / rollback / close。
- 多步写入要么放同一事务（如 `mark_snapshot_ready` 里的 `stale` + `ready`），要么显式设计补偿（如上传失败的孤儿清理）。
- 状态更新尽量用 CAS（`WHERE id=? AND status='...'`），返回值判断是否真的更新成功。

### 3.3 契约与命名

- 后端 Pydantic 模型全部 snake_case，无 alias；前端 `api.ts` 手写镜像。
- 新增/修改契约字段时**同步改前端**，否则前端拿到 `undefined` 且无编译错误。
- 面向用户的提示文案统一走 `settings.msg_*`，便于统一措辞。

### 3.4 日志

- `logging.basicConfig(INFO)` 在 `app/main.py` 导入期配置。
- 后台异常一律 `logger.exception`，不向前端泄露堆栈；对用户只返回泛化文案。

## 4. 常见改动 how-to

### 4.1 新增一个 HTTP 端点

1. 在 `app/contracts.py` 定义请求/响应模型。
2. 在 `app/services/` 加编排函数（不写 SQL）。
3. 在对应 `app/routes/*.py` 加 `@router.<method>`，绑定 `Depends(get_current_user)`。
4. 新 router 才需要在 `main.py` `include_router`。
5. 更新 [04 API 参考](04-api.md) 与前端 `api.ts`。

### 4.2 新增配置项

1. 在 `RuntimeSettings` 增加字段（带默认值，避免破坏现有 `.env`）。
2. 需要时在消费侧读取 `settings.<field>`，不要在模块内硬编码。
3. 在 [08 配置参考](08-configuration.md) 补充说明与默认值。

注意：`settings` 在 import 时实例化，改字段后需重启；`.env` 位于仓库根目录。

### 4.3 新增解析后端

1. 实现 `ParserBackend`（`name`、`version`、`parse`），返回 `RawParserResult`。
2. 在 `rag/ingestion/pipeline._build_parser_chain` 按优先级插入。
3. 若返回 `pages`，归一化可利用 bbox 做双栏/页眉页脚处理；只返回 `markdown` 也能工作（走 markdown 兜底切块）。
4. 补一个 `parser_backend=` 定位的单后端测试。

### 4.4 改数据表结构

1. `schema.py` 的建表 DDL 改为最新形态（影响新库）。
2. `CURRENT_SCHEMA_VERSION` +1，在 `_migrate_schema` 加对应版本分支（影响旧库）。
3. 若改外键，参考 v4 的 `foreign_keys = OFF` → 建 `*_new` → 拷数据 → `DROP` → `RENAME` → 重建索引 → `ON` 流程。
4. 更新仓储函数与 [03 数据模型与存储](03-data-model.md)。

### 4.5 调整检索参数

改 `.env` 即可，无需改代码。但注意 [06 检索与问答](06-retrieval-and-chat.md) 第 3 节的"三套默认值"：改 dataclass 默认值不会影响线上，线上只读 `settings`。

### 4.6 迁移旧数据目录

```bash
uv run --project backend python -m backend.scripts.migrate_storage \
  --source-data-dir data --target-data-dir backend/data
```

逐文件移动；同名且内容不同会 `RuntimeError("Storage migration conflict")`，需人工处理后再重跑。

## 5. 排障 FAQ

| 现象 | 原因 | 处理 |
|---|---|---|
| 登录返回 400 `Auth not configured` | `JWT_SECRET_KEY` 为空 | 设置 `JWT_SECRET_KEY` 后重启；或本地用 `localStorage.setItem("scipal_token","dev")` 绕过前端登录页 |
| 所有请求 401 `Not authenticated` | 已启用鉴权但没带 token | 前端重新登录；`api.ts` 从 `localStorage["scipal_token"]` 取 |
| 上传 413 | 超过 `UPLOAD_MAX_BYTES`（50 MiB） | 调大配置或压缩 PDF |
| 上传 400 `not a valid PDF` | 前 4 字节不是 `%PDF` | 确认文件确为 PDF |
| 上传 404 `Please create a session first` | `session_id` 不存在 | 先 `POST /sessions` |
| 文档一直 `parsing` | MinerU 进程卡住/模型下载中 | 看后端日志；本地解析超时 600s；可改用 `MINERU_API_KEY` 走云解析 |
| 文档 `failed` 且 `PDF_TEXT_NOT_EXTRACTABLE` | 扫描版/图片型 PDF | 当前不支持，需先 OCR |
| 文档 `failed` 且 `NO_RETRIEVABLE_CHUNKS` | 解析结果无可用文本块 | 检查 PDF 文本层与解析日志 |
| 对话返回"论文仍在处理中" | 10s 内未出现 ready 快照 | 等文档 `ready` 后重问；多文档排队时可调大 `INDEX_MAX_WAIT` |
| 回答没有任何依据 | 检索为空或引用校验失败 | 查 `sources` 是否为空；确认文档已 `ready` 且 chunks 非空 |
| `Embedding dimension mismatch` | `EMBEDDING_DIM` 与模型输出不一致 | 改正维度并对已有文档重建索引 |
| 模型下载失败 / 启动时卡在加载权重 | 网络不通或 `EMBEDDING_MODEL_SOURCE` 选错 | 预下载权重到 `model_cache/embeddings/` 并设 `EMBEDDING_LOCAL_FILES_ONLY=true`；本地 embedder 失败后会退避 60s→600s 再重试 |
| 前端请求被 CORS 拦 | 用非 localhost 访问 | 调整 `CORS_ORIGIN_REGEX`，或改 `VITE_API_BASE_URL` 同源部署 |
| 数据库"消失" | 默认 DB 落在源码包或 `SCIPAL_DATA_DIR` 被改 | 查 `SCIPAL_DB_PATH` / `SCIPAL_DATA_DIR`，见 08 章第 3 节 |

## 6. 运行与运维要点

- **单实例假设**：`InProcessJobRunner` 是进程内线程，多副本部署会导致同一 job 被并发领取（CAS 能防重复领取，但索引文件与会话锁只在进程内有效）。需要横向扩展时应先把任务层外置。
- **备份**：需同时备份 SQLite 文件（含 `-wal` / `-shm`）与 `<data>/raw`、`<data>/index`。只备份 DB 会丢索引文件，需重建。
- **磁盘增长**：每次重建索引都会产生新快照文件，旧 `stale` 快照**不会自动清理**（保留用于回滚），长期运行需人工清理或补 GC。
- **启动恢复**：进程被杀后重启会把 `running` / `interrupted` job 重新排队；`uploaded` 但无 job 的孤儿文档会被清理。
- **日志**：默认 INFO 输出到 stdout；异常堆栈只在服务端日志，前端只看到泛化文案。

## 7. 仓库与工程约定

- `openspec/`：spec-driven change 归档，命名 `archive/<YYYY-MM-DD>-<kebab-name>/`，每个 change 含 `.openspec.yaml` + `proposal.md` + `design.md` + `tasks.md`。当前**没有 `openspec/specs/`**，两个已归档 change 都设置了 `skip_specs: true`。
- `.gitignore` 关键项：`data/`、`backend/data/`、`.env`、`tests/`、`eval_outputs/`、`docs/`、`*.db` 及 `-wal`/`-shm`。
  - 即：**测试、评测产物、数据集、文档默认都不入库**。若要让本 Wiki 进版本库，需要把 `docs/` 改为 `docs/*` + `!docs/wiki/`（或删除该行）。
- `frontend/README.md` 是未清理的 React 模板，不要参考。
- 没有 `CLAUDE.md` / `AGENTS.md`。

## 8. 已知缺口（按影响排序）

1. **无任何自动化测试**，且 `tests/` 被 gitignore，回归风险高。
2. **资源归属未校验**：知道 `session_id` 即可跨用户读写（`routes/*` 只取 `user` 不比较 `session.user_id`）。
3. **多副本不可用**：任务队列与向量库缓存均为进程内状态。
4. **旧快照不回收**：索引文件随重建次数线性增长。
5. **前端路由表是死代码**：`main.ts` 未注册 router。
6. **`status` 事件未消费**：前端无细粒度进度。
7. **`cancelled` 状态无写入路径**：任务取消能力缺失。
8. **无 token 预算**：上下文只按块数限制。
