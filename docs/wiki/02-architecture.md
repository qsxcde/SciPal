# 02 系统架构

## 1. 分层视图

```
┌──────────────────────────────────────────────────────────────┐
│ 展示层  frontend/src（Vue 3）                                  │
│         api.ts（REST + SSE 客户端）→ /sessions /documents ...   │
└───────────────────────────┬──────────────────────────────────┘
                            │ HTTP + text/event-stream
┌───────────────────────────▼──────────────────────────────────┐
│ 接口层  backend/api/                                          │
│         routes/*（路由） schemas/*（传输契约）                  │
│         deps.py（授权依赖） streaming.py（SSE 编码）            │
│         errors.py（领域异常 → HTTP） security.py（JWT）         │
├──────────────────────────────────────────────────────────────┤
│ 应用层  backend/application/                                  │
│         sessions / documents / ingestion / indexing           │
│         chat / evaluation（评测用例）                          │
│         store_cache（索引 LRU） session_index / policies        │
│         只做编排与状态流转，不依赖 Web 框架                     │
├──────────────────────────────────────────────────────────────┤
│ 领域层  backend/domain/                                       │
│         models.py（Pydantic 模型）states.py（枚举）            │
│         access.py（授权规则）exceptions.py                     │
├──────────────────────────────────────────────────────────────┤
│ 能力层                                                        │
│  rag/ingestion   rag/indexing   rag/retrieval                 │
│  rag/generation  rag/embedding  rag/answer.py                 │
├──────────────────────────────────────────────────────────────┤
│ 存储层  backend/storage/                                      │
│  sqlite/*（8 张表仓储）  paths.py（目录布局）                   │
└──────────────────────────────────────────────────────────────┘
```

依赖方向是单向的：`api → application → (domain, rag, storage)`。`storage/*` 不依赖 `rag/*`；`rag/*` 不依赖 `api` / `application`，也不读全局配置；`domain/*` 不依赖任何上层模块。装配（settings、runner、异常处理器、job handler）只发生在 `backend/main.py`。

## 2. 模块职责

### 2.1 接口层 `backend/src/backend/api/`（装配根在 `backend/main.py`）

| 文件 | 职责 |
|---|---|
| `backend/main.py` | 装配根：`init_db` → 孤儿文档清理 → 中断 job 重排 → 启动 runner；注册 CORS、异常处理器、job handler 与 4 个 router；`/health` |
| `api/schemas/{auth,session,document,chat}.py` | 请求/响应与 SSE 事件的 Pydantic 模型，按域拆分，无 alias |
| `api/security.py` | `OAuth2PasswordBearer` + JWT 签发/校验 + bcrypt 口令哈希 |
| `api/deps.py` | `get_accessible_session`：授权规则的唯一调用入口，失败抛 `SessionNotFoundError` |
| `api/errors.py` | 领域异常 → HTTP 映射（404 / 413 / 400），是唯一的错误翻译点 |
| `api/streaming.py` | 应用事件 → SSE `data: {...}\n\n` |
| `api/routes/sessions.py` | 会话 CRUD 与快照读取 |
| `api/routes/documents.py` | PDF 上传（`multipart`，字段名 `file`），返回 `202` |
| `api/routes/chat.py` | SSE 端点；只做事件编码与客户端断连处理 |
| `api/routes/auth.py` | 注册 / 登录 / `me` |
| `worker/runner.py` | `InProcessJobRunner`：FIFO 取任务、会话级串行锁、崩溃恢复、handler 注册表 |
| `worker/handlers.py` | `document_ingestion` handler：读 PDF 字节 → 调摄服用例 → 标记 job 完成 |

### 2.2 应用层

| 模块 | 职责边界 | 关键事实 |
|---|---|---|
| `sessions.py` | 会话聚合与派生状态 | `get_session_snapshot` 一次聚合 6 张表；归档会话返回 `None` |
| `documents.py` | 上传落地与启动清理 | 文件写盘 + `documents` / `jobs` 行 + 回滚补偿；失败抛领域异常，不再依赖 `HTTPException` |
| `ingestion.py` | 单次摄取的状态机 | 解析 → 产物落盘 → 切块 → 建候选快照 → 提交；失败统一 `_mark_failed` |
| `indexing.py` | 索引两阶段发布 | `build_candidate_snapshot` / `commit_ready_snapshot` / 回滚 / 文件清理 |
| `chat.py` | 一次问答的用例 | 等索引、持久化消息、调用 RAG、产出 `application.events` 事件；不认识 SSE |
| `evaluation.py` | 评测用例 | `evaluate_session_chat` / `evaluate_session_retrieval`，仅供 `scipal_eval` CLI |
| `store_cache.py` | 向量库进程内缓存 | `session_id → FAISSVectorStore` 的 LRU（容量 16） |
| `session_index.py` | 索引解析与等待 | 取 active ready 快照，指数退避等待 |
| `policies.py` | 配置 → 能力参数 | 把 `settings` 翻译成 `RetrievalOptions` / `AnswerPolicy` |

### 2.3 领域层 `backend/src/backend/domain/`

- `models.py`：`ChunkMetadata`、`Chunk`、`SourceRef`，全部 Pydantic `BaseModel`（非 dataclass）。
- `states.py`：`SessionStatus`、`DocumentStage`、`IndexSnapshotStatus`、`JobStatus` 四个 `StrEnum`，外加 `TERMINAL_JOB_STATUSES` 与 `PROCESSING_DOCUMENT_STAGES` 两个常量集合。
- `access.py`：`session_is_accessible`，纯函数授权规则。
- `exceptions.py`：`PaperParseError`、`EmbeddingModelUnavailableError`、`SessionNotFoundError`、`ActiveIndexNotReadyError`、`SnapshotCommitError`，以及上传校验用的 `UploadValidationError` / `UploadTooLargeError` / `InvalidUploadError`。

> `RuntimeSettings` 不在 domain 内：见 `backend/config.py`（2.6）。

### 2.4 能力层 `backend/src/backend/rag/`

| 包 | 关键入口 | 说明 |
|---|---|---|
| `ingestion/` | `pipeline.process_pdf_document` | 解析器链 + 归一化 + 切块，纯函数式，不碰数据库 |
| `indexing/` | `vector_store.FAISSVectorStore` / `create_vector_store` | FAISS 封装：`add_chunks` / `search_with_ranks` / `save` / `load` |
| `retrieval/` | `hybrid_retriever.retrieve_hybrid_context` | BM25 + Dense + RRF + Rerank + 上下文扩展 |
| `generation/` | `answer_generator.stream_answer`、`model_client` | 提示词拼装、多 provider 降级、流式 token |
| `embedding/` | `embedding.create_embed_fn` | 远程 → 本地链式选择；输入上限集中在 `embedding/limits.py` |
| `ingestion/render.py` | `render_block` / `ordered_blocks` | DocumentIR 渲染的唯一入口：chunk 正文与导出 Markdown 共用，避免两套渲染漂移 |
| `llm_output.py` | `strip_markdown_fence` / `parse_json_object` | LLM 结构化输出的统一清洗；改写/术语扩展/Judge 都走这里 |
| `resources.py` | `LazyResource` | 外部客户端（OpenAI / httpx）的线程安全懒加载单例 |
| `answer.py` | `answer.stream_answer` | 单轮问答能力（检索 + 生成 + 引用校验）；`options` 与 `policy` 必须由调用方显式传入 |

### 2.5 存储层

| 文件 | 职责 |
|---|---|
| `storage/paths.py` | 会话目录布局；`remove_session_dir` 带越界校验 |
| `storage/sqlite/connection.py` | 路径三级回退、PRAGMA、`transaction()` 上下文管理器 |
| `storage/sqlite/schema.py` | DDL、`init_db()`、`PRAGMA user_version` 增量迁移 |
| `storage/sqlite/{sessions,documents,jobs,chunks,messages,indexes,index_snapshots,users}.py` | 各表仓储函数（无 ORM，纯 SQL） |

### 2.6 配置 `backend/src/backend/config.py`

`RuntimeSettings`（全量字段见 08 章）、`Settings`（强制 `DEEPSEEK_API_KEY`）、模块级单例 `settings`、`data_dir()` / `model_dir()` 等路径函数。能力层不得直接 import 它，只能通过 `application/policies.py` 注入参数。

提示词统一由 `backend/prompts/loader.py::load_prompt(section, key="system", default=None)` 读取 `prompts.toml`；`default` 仅用于允许降级的场景，缺 section 且无 `default` 时直接抛 `KeyError`。

## 3. 启动时序

`backend/src/backend/main.py`

```
import 期
  settings = RuntimeSettings()     # 读取仓库根 .env
  runner   = InProcessJobRunner()  # 仅构造，不启动线程

lifespan 启动
  1. await to_thread(init_db)
        user_version < 1 → 直接建当前全量 schema 并置 5
        否则逐版本迁移 v2 → v5
  2. await to_thread(recover_orphaned_documents)
        删除 status=uploaded 且无对应 job 的文档行与磁盘文件；异常仅记日志
  3. await to_thread(runner.recover_interrupted_jobs)
        running / interrupted → queued（清 started_at / finished_at / error）
  4. runner.start()   # daemon 线程名 scipal-job-runner
  5. yield
  关闭
  runner.stop(timeout=1.0)  # 超时仅告警
```

要点：

- 恢复步骤异常都不会阻断启动（`logger.exception` 后继续）。
- 没有 DI 容器，也没有 `app.state`；`settings` 与 `runner` 都是模块级单例。
- CORS 使用 `allow_origin_regex`（默认仅 `localhost` / `127.0.0.1` 任意端口），未开启 `allow_credentials`。

## 4. 请求生命周期

### 4.1 读取会话快照

```
GET /sessions/{id}
  → get_current_user（可选 Bearer）
  → application.sessions.get_session_snapshot
        storage.sqlite.sessions.get_session
        storage.sqlite.documents.list_documents
        storage.sqlite.messages.list_messages
        storage.sqlite.chunks.count_chunks
        storage.sqlite.indexes.get_index
        storage.sqlite.index_snapshots.get_active_ready_snapshot
        storage.sqlite.jobs.list_jobs_for_session
        _derive_session_status（由文档状态集合派生）
  → 200 SessionSnapshot | 404（SessionNotFoundError 由 api/errors.py 映射）
```

### 4.2 上传文档

```
POST /sessions/{id}/documents
  → Depends(get_accessible_session)      # 授权唯一入口，失败抛 SessionNotFoundError
  → application.documents.intake_document_upload
        _validate_upload（大小 → UploadTooLargeError、%PDF 魔数 → InvalidUploadError）
        storage.paths.session_document_file_path → 写 PDF
        storage.sqlite.documents.create_document(status=uploaded)
        storage.sqlite.jobs.create_job(status=queued, stage=uploaded, payload_json={document_id, filename, file_path})
        storage.sqlite.sessions.touch_session
        title == 默认标题 → update_session_title(文件名)
  → 202 DocumentIntakeResponse
```

同步路径不触发任何解析，故响应时间与文件大小基本无关（整包读入内存）。

### 4.3 流式问答

```
POST /sessions/{id}/messages
  → Depends(get_accessible_session)      # 授权唯一入口
  → application.chat.stream_session_chat      # 产出 application.events 事件
        storage.sqlite.sessions.get_session → 不存在/已归档 → SessionNotFoundError
        application.session_index.resolve_session_store
        └── 无 ready 快照 → wait_for_ready_index（指数退避，总预算 index_max_wait）
        store_cache.get_store_for_snapshot
        storage.sqlite.messages.list_messages（取历史，供历史改写）
        storage.sqlite.messages.create_message(role=user)
        rag.answer.stream_answer(store, content, options=policies.retrieval_options(),
                                 policy=policies.answer_policy(), history=...)
        StreamCollector.consume_stream：转发 token、累积全文与 sources
        storage.sqlite.messages.create_message(role=assistant, sources=..., status=complete|failed)
  → api.streaming.encode_sse_event → 200 text/event-stream
```

## 5. 并发模型

| 面 | 实现 | 约束 |
|---|---|---|
| HTTP / SSE | asyncio 事件循环 | SSE 生成器内所有同步阻塞调用需经 `run_in_executor`，见 `chat.StreamCollector.consume_stream` |
| 摄取任务 | 单 daemon 线程 | 每 tick 只取 1 条 job；同一 `session_id` 用 `threading.Lock` 串行 |
| SQLite | 每操作短连接 + `transaction()` | WAL + `busy_timeout=5000`；写操作尽量收敛在单事务 |
| 向量库 | 进程内 LRU（16）+ `discard_store` 失效 | 提交快照后主动失效，避免读到旧索引 |
| 模型加载 | 进程级单例 | 本地 embedding 加载失败带指数退避（60s→600s） |

任务领取是乐观并发：`mark_job_running` 使用 `WHERE id=? AND status='queued'` 的 CAS，保证同一 job 不会被重复执行。

## 6. 错误处理分层

| 层 | 手段 | 表现 |
|---|---|---|
| 路由层 | `HTTPException`（仅限 `auth` 的传输级校验） | 4xx + `detail` 文案 |
| 异常映射 | `api/errors.py` | `SessionNotFoundError` → 404、`UploadTooLargeError` → 413、`UploadValidationError` → 400 |
| 应用层 | 领域异常 + 状态落库 | 摄取失败 → 文档 `failed` + job `failed` + 快照 `failed`；用例层不 import `fastapi` |
| SSE 层 | 事件化错误 | HTTP 仍 200，通过 `error` / `warning` 事件表达；客户端断开只记日志 |
| 领域层 | 带上下文的异常对象 | `PaperParseError(session_id, document_id)`、`SnapshotCommitError(preserve_candidate_snapshot_files=...)` |
| 日志 | `logging.basicConfig`（INFO，在 `main.py` 装配） | 异常统一 `logger.exception`，不向前端泄露堆栈 |

副作用（标记 failed、删文件、清 chunks）不写在异常类里，而集中在 `ingestion._mark_failed`，便于单点维护。

## 7. 关键契约

- **字段命名**：后端契约全部 snake_case，无 Pydantic alias；前端 `api.ts` 手写镜像同样 snake_case。
- **SSE 分帧**：只写 `data:` 行，空行分帧，不使用 `event:` / `id:` / `retry:`；业务类型由 JSON 内 `type` 字段区分。
- **状态派生**：`SessionStatus` 不落库，任何时刻由文档状态集合推导；前端不要缓存该值。
- **索引可见性**：对外可用索引 = `index_snapshots` 中 active `ready` 快照；`retrieval_indexes` 为 legacy 兼容读取路径。
- **资源归属**：策略在 `domain/access.session_is_accessible`，调用入口在 `api/deps.get_accessible_session`；`user_id IS NULL` 的历史会话对所有调用方开放，其余必须与当前用户一致，否则按 404 处理。
- **依赖边界**：`tests/test_package_boundaries.py` 用 AST 静态校验「application 不依赖 fastapi」「storage 不依赖 rag」「rag/answer 不读 settings」「仅 api 与 main 依赖 fastapi」。

细节见 [04 API 参考](04-api.md) 与 [03 数据模型与存储](03-data-model.md)。
