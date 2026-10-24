# 02 系统架构

## 1. 分层视图

```
┌──────────────────────────────────────────────────────────────┐
│ 展示层  frontend/src（Vue 3）                                  │
│         api.ts（REST + SSE 客户端）→ /sessions /documents ...   │
└───────────────────────────┬──────────────────────────────────┘
                            │ HTTP + text/event-stream
┌───────────────────────────▼──────────────────────────────────┐
│ 接口层  backend/app/routes/*.py                                │
│         auth / sessions / documents / chat                    │
│         依赖：Depends(get_current_user)                        │
├──────────────────────────────────────────────────────────────┤
│ 应用服务层  backend/app/services/*.py                          │
│         session / document / ingestion / index / chat          │
│         只做编排与状态流转，不直接实现解析/检索算法              │
├──────────────────────────────────────────────────────────────┤
│ 领域层  backend/domain/                                       │
│         models.py（Pydantic 模型）states.py（枚举）            │
│         config.py（RuntimeSettings）exceptions.py              │
├──────────────────────────────────────────────────────────────┤
│ 能力层                                                        │
│  rag/ingestion      rag/indexing     rag/retrieval            │
│  rag/generation     rag/embedding    rag/pipeline             │
├──────────────────────────────────────────────────────────────┤
│ 存储层  backend/storage/                                      │
│  sqlite/*（8 张表仓储）  paths.py（目录布局）                   │
│  vector_db/registry.py（FAISS 实例 LRU 缓存）                  │
└──────────────────────────────────────────────────────────────┘
```

依赖方向是单向的：`routes → services → (domain, storage, rag)`。`rag/*` 与 `storage/*` 互不反向依赖应用层；`domain/*` 不依赖任何上层模块。

## 2. 模块职责

### 2.1 接口层 `backend/src/backend/app/`

| 文件 | 职责 |
|---|---|
| `main.py` | 应用工厂与生命周期：`init_db` → 孤儿文档清理 → 中断 job 重排 → 启动 runner；注册 CORS 与 4 个 router；`/health` |
| `contracts.py` | 全部请求/响应 Pydantic 模型（`SessionSummary`、`SessionSnapshot`、`DocumentSummary`、`JobSummary`、`IndexSnapshotSummary`、`ChatMessage` 与 6 种 SSE 事件） |
| `security.py` | `OAuth2PasswordBearer` + JWT 签发/校验 + bcrypt 口令哈希 |
| `runner.py` | `InProcessJobRunner`：FIFO 取任务、会话级串行锁、崩溃恢复、健康状态 |
| `routes/sessions.py` | 会话 CRUD 与快照读取 |
| `routes/documents.py` | PDF 上传（`multipart`，字段名 `file`），返回 `202` |
| `routes/chat.py` | SSE 端点；只负责把事件序列化成 `data: {...}\n\n` |
| `routes/auth.py` | 注册 / 登录 / `me` |

### 2.2 应用服务层

| 服务 | 职责边界 | 关键事实 |
|---|---|---|
| `session_service` | 会话聚合与派生状态 | `get_session_snapshot` 一次聚合 6 张表；归档会话返回 `None` → 路由 404 |
| `document_service` | 上传落地与启动清理 | 文件写盘 + `documents` / `jobs` 行 + 回滚补偿；`recover_orphaned_documents` 清理无 job 的 `uploaded` 文档 |
| `ingestion_service` | 单次摄取的状态机 | 解析 → 产物落盘 → 切块 → 建候选快照 → 提交；失败统一 `_mark_failed` |
| `index_service` | 索引两阶段发布 | `build_candidate_snapshot` / `commit_ready_snapshot` / 回滚 / 文件清理 |
| `chat_service` | SSE 协议状态机 | 等索引、持久化消息、调在线管线、异常兜底；`evaluate_*` 仅供评测 CLI 使用 |

### 2.3 领域层 `backend/src/backend/domain/`

- `models.py`：`ChunkMetadata`、`Chunk`、`SourceRef`，全部 Pydantic `BaseModel`（非 dataclass）。
- `states.py`：`SessionStatus`、`DocumentStage`、`IndexSnapshotStatus`、`JobStatus` 四个 `StrEnum`，外加 `TERMINAL_JOB_STATUSES` 与 `PROCESSING_DOCUMENT_STAGES` 两个常量集合。
- `config.py`：`RuntimeSettings`（全量字段，见 08 章）、`Settings`（强制 `DEEPSEEK_API_KEY`）、模块级单例 `settings`、`data_dir()` / `model_dir()` 等路径函数。
- `exceptions.py`：`PaperParseError`、`EmbeddingModelUnavailableError`、`SessionNotFoundError`、`ActiveIndexNotReadyError`、`SnapshotCommitError`。

### 2.4 能力层 `backend/src/backend/rag/`

| 包 | 关键入口 | 说明 |
|---|---|---|
| `ingestion/` | `pipeline.process_pdf_document` | 解析器链 + 归一化 + 切块，纯函数式，不碰数据库 |
| `indexing/` | `vector_store.FAISSVectorStore` / `create_vector_store` | FAISS 封装：`add_chunks` / `search_with_ranks` / `save` / `load` |
| `retrieval/` | `hybrid_retriever.retrieve_hybrid_context` | BM25 + Dense + RRF + Rerank + 上下文扩展 |
| `generation/` | `answer_generator.stream_answer`、`model_client` | 提示词拼装、多 provider 降级、流式 token |
| `embedding/` | `embedding.create_embed_fn` | 远程 → 本地链式选择 |
| `pipeline/` | `online_pipeline.stream_answer` | 在线问答编排（检索 + 生成 + 引用校验） |

### 2.5 存储层

| 文件 | 职责 |
|---|---|
| `storage/paths.py` | 会话目录布局；`remove_session_dir` 带越界校验 |
| `storage/sqlite/connection.py` | 路径三级回退、PRAGMA、`transaction()` 上下文管理器 |
| `storage/sqlite/schema.py` | DDL、`init_db()`、`PRAGMA user_version` 增量迁移 |
| `storage/sqlite/{sessions,documents,jobs,chunks,messages,indexes,index_snapshots,users}.py` | 各表仓储函数（无 ORM，纯 SQL） |
| `storage/vector_db/registry.py` | `session_id → FAISSVectorStore` 的进程内 LRU（容量 16） |

## 3. 启动时序

`backend/src/backend/app/main.py:26-44`

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
  → session_service.get_session_snapshot
        sessions.get_session
        documents.list_documents
        messages.list_messages
        chunks.count_chunks
        indexes.get_index
        index_snapshots.get_active_ready_snapshot
        jobs.list_jobs_for_session
        _derive_session_status（由文档状态集合派生）
  → 200 SessionSnapshot | 404
```

### 4.2 上传文档

```
POST /sessions/{id}/documents
  → document_service.intake_document_upload
        _validate_upload（大小、%PDF 魔数）
        paths.session_document_file_path → 写 PDF
        documents.create_document(status=uploaded)
        jobs.create_job(status=queued, stage=uploaded, payload_json={document_id, filename, file_path})
        sessions.touch_session
        title == 默认标题 → update_session_title(文件名)
  → 202 DocumentIntakeResponse
```

同步路径不触发任何解析，故响应时间与文件大小基本无关（整包读入内存）。

### 4.3 流式问答

```
POST /sessions/{id}/messages
  → chat_service.stream_session_chat
        sessions.get_session → 不存在/已归档 → SessionNotFoundError
        index_snapshots.get_active_ready_snapshot
        └── 无 → _wait_for_ready_index（指数退避，总预算 index_max_wait）
        registry.get_store_for_snapshot
        messages.list_messages（取历史，供历史改写）
        messages.create_message(role=user)
        online_pipeline.stream_answer(store, content, options=production_retrieval_options(), history=...)
        consume_stream：转发 token、累积全文
        messages.create_message(role=assistant, sources=..., status=complete|failed)
  → 200 text/event-stream
```

## 5. 并发模型

| 面 | 实现 | 约束 |
|---|---|---|
| HTTP / SSE | asyncio 事件循环 | SSE 生成器内所有同步阻塞调用需经 `run_in_executor`，见 `chat_service.consume_stream` |
| 摄取任务 | 单 daemon 线程 | 每 tick 只取 1 条 job；同一 `session_id` 用 `threading.Lock` 串行 |
| SQLite | 每操作短连接 + `transaction()` | WAL + `busy_timeout=5000`；写操作尽量收敛在单事务 |
| 向量库 | 进程内 LRU（16）+ `discard_store` 失效 | 提交快照后主动失效，避免读到旧索引 |
| 模型加载 | 进程级单例 | 本地 embedding 加载失败带指数退避（60s→600s） |

任务领取是乐观并发：`mark_job_running` 使用 `WHERE id=? AND status='queued'` 的 CAS，保证同一 job 不会被重复执行。

## 6. 错误处理分层

| 层 | 手段 | 表现 |
|---|---|---|
| 路由层 | `HTTPException` | 4xx + `detail` 文案（`Session not found`、`File too large` 等） |
| 应用服务层 | 领域异常 + 状态落库 | 摄取失败 → 文档 `failed` + job `failed` + 快照 `failed` |
| SSE 层 | 事件化错误 | HTTP 仍 200，通过 `error` / `warning` 事件表达；客户端断开只记日志 |
| 领域层 | 带上下文的异常对象 | `PaperParseError(session_id, document_id)`、`SnapshotCommitError(preserve_candidate_snapshot_files=...)` |
| 日志 | `logging.basicConfig`（INFO） | 异常统一 `logger.exception`，不向前端泄露堆栈 |

副作用（标记 failed、删文件、清 chunks）不写在异常类里，而集中在 `ingestion_service._mark_failed`，便于单点维护。

## 7. 关键契约

- **字段命名**：后端契约全部 snake_case，无 Pydantic alias；前端 `api.ts` 手写镜像同样 snake_case。
- **SSE 分帧**：只写 `data:` 行，空行分帧，不使用 `event:` / `id:` / `retry:`；业务类型由 JSON 内 `type` 字段区分。
- **状态派生**：`SessionStatus` 不落库，任何时刻由文档状态集合推导；前端不要缓存该值。
- **索引可见性**：对外可用索引 = `index_snapshots` 中 active `ready` 快照；`retrieval_indexes` 为 legacy 兼容读取路径。

细节见 [04 API 参考](04-api.md) 与 [03 数据模型与存储](03-data-model.md)。
