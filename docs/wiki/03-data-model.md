# 03 数据模型与存储

权威定义：`backend/src/backend/storage/sqlite/schema.py`（`CURRENT_SCHEMA_VERSION = 5`）。
仓储实现：`backend/src/backend/storage/sqlite/*.py`（纯 SQL，无 ORM）。

## 1. 表总览

| 表 | 粒度 | 关键作用 |
|---|---|---|
| `sessions` | 会话 | 标题、置顶、归档、归属用户 |
| `documents` | 文档 | PDF 元数据、状态机、解析产物路径 |
| `chunks` | 分块 | 检索事实表，正文 + 结构化元数据 |
| `messages` | 消息 | 对话历史与 `sources_json` |
| `jobs` | 任务 | 单次摄取尝试、重试次数、错误 |
| `index_snapshots` | 索引快照 | 不可变快照与原子切换 |
| `retrieval_indexes` | 已发布索引 | legacy 兼容的"当前索引指针" |
| `users` | 用户 | 登录账号（v5 引入） |

## 2. 表结构

### 2.1 `sessions`

| 列 | 类型 | 约束 / 默认 | 说明 |
|---|---|---|---|
| `id` | TEXT | PK | UUID |
| `title` | TEXT | NOT NULL | 默认取 `settings.msg_default_session_title`（"新论文会话"）；首次上传时若仍是默认值则改为文件名 |
| `user_id` | TEXT | NULL | 归属用户，**无外键**（弱关联） |
| `created_at` | TEXT | NOT NULL | ISO8601 UTC |
| `updated_at` | TEXT | NOT NULL | 任何写操作刷新 |
| `last_opened_at` | TEXT | NOT NULL | 与 `updated_at` 同步更新 |
| `is_archived` | INTEGER | NOT NULL DEFAULT 0 | 软删除标记 |
| `is_pinned` | INTEGER | NOT NULL DEFAULT 0 | 置顶排序 |

索引：`idx_sessions_list ON sessions(is_archived, is_pinned, updated_at DESC) WHERE is_archived = 0`（部分索引，v3 引入）。

> `sessions` 表**没有** `status` 列——`SessionStatus` 是运行时派生值。

### 2.2 `documents`

| 列 | 类型 | 约束 / 默认 | 说明 |
|---|---|---|---|
| `id` | TEXT | PK | UUID，同时是 PDF 文件名主干 |
| `session_id` | TEXT | NOT NULL, FK → `sessions.id` CASCADE | |
| `filename` | TEXT | NOT NULL | 原始文件名 |
| `file_path` | TEXT | NOT NULL | `<data>/raw/<session_id>/<document_id>.pdf` |
| `mime_type` | TEXT | NOT NULL | |
| `file_size` | INTEGER | NOT NULL | 字节数 |
| `chunk_count` | INTEGER | NOT NULL DEFAULT 0 | 冗余计数，插入/删除 chunks 时同事务重算 |
| `status` | TEXT | NOT NULL | `DocumentStage` |
| `error_message` | TEXT | NULL | 失败原因 |
| `created_at` / `updated_at` | TEXT | NOT NULL | |
| `parsed_ir_path` | TEXT | NULL | `document.ir.json` |
| `parsed_markdown_path` | TEXT | NULL | `document.md` |
| `quality_report_path` | TEXT | NULL | `quality_report.json` |
| `parser_name` / `parser_version` | TEXT | NULL | 命中的解析后端 |
| `parse_quality_status` | TEXT | NULL | `QualityReport.overall_status` |

索引：`idx_documents_session_id`、`idx_documents_status`。

注意：`update_document_status` 每次都会覆盖 `error_message`（未传即为 `NULL`），成功推进阶段时错误信息会被清掉。

### 2.3 `chunks`

| 列 | 类型 | 约束 / 默认 | 说明 |
|---|---|---|---|
| `id` | TEXT | PK | UUID |
| `session_id` | TEXT | NOT NULL, FK CASCADE | |
| `document_id` | TEXT | NOT NULL, FK → `documents.id` CASCADE | 即 `ChunkMetadata.paper_id` |
| `section` | TEXT | NOT NULL | `" > "` 拼接的章节路径 |
| `chunk_index` | INTEGER | NOT NULL | 文档内序号 |
| `text_excerpt` | TEXT | NOT NULL | 正文前 240 字符 |
| `text_content` | TEXT | NOT NULL | 完整正文 |
| `type` | TEXT | NOT NULL | `abstract/paragraph/table/heading/formula/code/caption/reference` |
| `created_at` | TEXT | NOT NULL | |
| `section_path_json` | TEXT | NULL | `list[str]` |
| `page_start` / `page_end` | INTEGER | NULL | |
| `bbox_json` | TEXT | NULL | `{x0,y0,x1,y1}` |
| `block_ids_json` / `block_types_json` / `linked_block_ids_json` | TEXT | NULL | `list[str]` |
| `confidence` | REAL | NULL | 合块取最小值 |

索引：`idx_chunks_session_id`、`idx_chunks_document_id`、`UNIQUE idx_chunks_unique_document_chunk(document_id, chunk_index)`（v2 引入）。

> `ChunkMetadata` 中的 `word_count` / `char_count` / `is_reference` **不落库**；`is_reference` 在检索期由章节名启发式判断（`rag/retrieval/filters.py`）。

### 2.4 `messages`

| 列 | 类型 | 约束 / 默认 | 说明 |
|---|---|---|---|
| `id` | TEXT | PK | UUID |
| `session_id` | TEXT | NOT NULL, FK CASCADE | |
| `role` | TEXT | NOT NULL | `user` / `assistant` |
| `content` | TEXT | NOT NULL | |
| `sources_json` | TEXT | NULL | `list[SourceRef]` 的 JSON |
| `status` | TEXT | NOT NULL DEFAULT `complete` | `complete` / `failed` / `stopped` |
| `created_at` | TEXT | NOT NULL | |

索引：`idx_messages_session_id`。

### 2.5 `jobs`

| 列 | 类型 | 约束 / 默认 | 说明 |
|---|---|---|---|
| `id` | TEXT | PK | UUID |
| `session_id` | TEXT | NOT NULL, FK CASCADE | |
| `document_id` | TEXT | NULL, FK → `documents.id` **SET NULL** | |
| `type` | TEXT | NOT NULL | 目前仅 `document_ingestion` |
| `status` | TEXT | NOT NULL | `JobStatus`，创建即 `queued` |
| `stage` | TEXT | NOT NULL | runner 只接受 `uploaded` |
| `attempt` | INTEGER | NOT NULL DEFAULT 0 | 进入 running 时 +1 |
| `error_message` | TEXT | NULL | |
| `payload_json` | TEXT | NULL | `{document_id, filename, file_path}` |
| `created_at` | TEXT | NOT NULL | |
| `started_at` / `finished_at` | TEXT | NULL | |

索引：`idx_jobs_session_status(session_id, status)`。

### 2.6 `index_snapshots`

| 列 | 类型 | 约束 / 默认 | 说明 |
|---|---|---|---|
| `id` | TEXT | PK | UUID（同时是候选文件 token） |
| `session_id` | TEXT | NOT NULL, FK CASCADE | |
| `status` | TEXT | NOT NULL | `building / ready / failed / stale` |
| `index_path` | TEXT | NOT NULL | `index/<sid>/snapshots/<token>.faiss.index` |
| `chunks_path` | TEXT | NOT NULL | `index/<sid>/snapshots/<token>.chunks.json` |
| `document_ids_json` | TEXT | NOT NULL | 该快照覆盖的文档 id 数组 |
| `error_message` | TEXT | NULL | 失败 / 回滚原因 |
| `created_at` / `updated_at` | TEXT | NOT NULL | |

索引：`idx_index_snapshots_session_status(session_id, status)`。

"每会话至多一个 `ready`"是**应用层不变量**，DB 未强制；读取用 `ORDER BY updated_at DESC LIMIT 1`。

### 2.7 `retrieval_indexes`（legacy 兼容层）

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | TEXT | PK | UUID |
| `session_id` | TEXT | NOT NULL, FK CASCADE | 逻辑 1:1，无 UNIQUE |
| `index_path` | TEXT | NOT NULL | 指向 active ready 快照的 FAISS 文件 |
| `chunks_path` | TEXT | NOT NULL | 指向快照的 sidecar |
| `status` | TEXT | NOT NULL | `ready` / `failed` |
| `created_at` / `updated_at` | TEXT | NOT NULL | |

每次快照发布/回滚都会 upsert 这行，使旧代码与旧缓存仍可工作。

### 2.8 `users`

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | TEXT | PK | UUID |
| `username` | TEXT | NOT NULL UNIQUE | 登录名（≥2 字符） |
| `hashed_password` | TEXT | NOT NULL | bcrypt |
| `created_at` / `updated_at` | TEXT | NOT NULL | |

## 3. 关系与文件系统映射

```
users ──(弱关联, 无 FK)── sessions
sessions 1 ── N documents     (CASCADE)
sessions 1 ── N messages      (CASCADE)
sessions 1 ── N chunks        (CASCADE)
sessions 1 ── N jobs          (CASCADE)
sessions 1 ── N index_snapshots (CASCADE)
sessions 1 ── 1 retrieval_indexes (逻辑, 无 UNIQUE)
documents 1 ── N chunks       (CASCADE)
documents 1 ── N jobs         (document_id 可空, SET NULL)
```

| 表.列 | 磁盘位置 |
|---|---|
| `documents.file_path` | `<data>/raw/<session_id>/<document_id>.pdf` |
| `documents.parsed_ir_path` | `<data>/raw/<session_id>/parsed/<document_id>/document.ir.json` |
| `documents.parsed_markdown_path` | `…/document.md` |
| （不入库） | `…/document.normalized.md` |
| `documents.quality_report_path` | `…/quality_report.json` |
| `index_snapshots.index_path` | `<data>/index/<session_id>/snapshots/<token>.faiss.index` |
| `index_snapshots.chunks_path` | `<data>/index/<session_id>/snapshots/<token>.chunks.json` |
| `retrieval_indexes.index_path` / `chunks_path` | 快照路径的指针拷贝；legacy 布局为 `index/<sid>/faiss.index` + `chunks.json` |

删除会话时：`archive_session`（置 `is_archived=1`）+ `registry.discard_store` + `remove_session_dir`（递归删除 `raw/`、`parsed/`、`chunks/`、`index/` 下该会话目录，删除前做 `is_relative_to` 越界校验）。

## 4. 状态机

### 4.1 文档 `DocumentStage`

```
                ┌─────────┐
                │uploaded │
                └────┬────┘
                     ▼
                ┌─────────┐    ┌────────┐    ┌─────────┐    ┌──────────┐    ┌───────┐
                │ parsing │───▶│ parsed │───▶│ chunked │───▶│ indexing │───▶│ ready │
                └─────────┘    └────────┘    └─────────┘    └──────────┘    └───────┘
                     │             │             │              │
                     └─────────────┴─────────────┴──────────────┴──────────▶ failed
```

- 触发点：`documents` 建行 → `uploaded`；`ingestion` 各阶段；`indexing` 提交成功后由 `update_document_status(ready)` 收尾。
- 无 `failed → *` 恢复路径；重试等价于重新上传一份新文档。
- `PROCESSING_DOCUMENT_STAGES = {processing, uploaded, parsing, parsed, chunked, indexing}`，其中 `processing` 仅为历史行保留。

### 4.2 任务 `JobStatus`

```
queued ──CAS──▶ running ──▶ succeeded
  ▲               │
  │               └──▶ failed
  └── 重启恢复 ── running / interrupted → queued（清 started_at / finished_at / error）
```

- 终态集合：`{succeeded, failed, cancelled, interrupted}`；向 `mark_job_finished` 传非终态抛 `ValueError("任务只能以终态结束")`。
- `cancelled` 枚举存在但**没有任何写入路径**。
- `attempt` 每次进入 running 时 +1，可作为重试计数。

### 4.3 索引快照 `IndexSnapshotStatus`

```
（新建）──▶ building ──▶ ready ──▶ stale
                │           │
                └──▶ failed ◀┘（发布失败回滚：ready→failed，stale→ready）
```

- `mark_snapshot_ready` 在**同一事务**内先把同会话其它 `ready` 置 `stale`，再把目标行 `building → ready`。
- 回滚函数 `rollback_snapshot_promotion` 逆向恢复：`stale → ready`、新快照 `ready → failed` 并写 `error_message`。
- 快照不可变：`stale` 不会回到 `building`，新构建总是新 UUID。

### 4.4 会话 `SessionStatus`（派生，不落库）

| 条件（自上而下） | 结果 |
|---|---|
| 无文档 | `empty` |
| 任一文档属于 `PROCESSING_DOCUMENT_STAGES` | `processing` |
| 全部 `ready` | `ready` |
| 同时存在 `failed` 与 `ready` | `degraded` |
| 全部 `failed` | `failed` |
| 其它 | `processing` |

## 5. 磁盘目录布局

```
backend/data/                              # 默认数据根 = backend_root().parent/"data"
├── raw/<session_id>/
│   ├── <document_id>.pdf                  # documents.file_path
│   └── parsed/<document_id>/
│       ├── document.ir.json
│       ├── document.md
│       ├── document.normalized.md
│       └── quality_report.json
├── index/<session_id>/
│   ├── faiss.index                        # legacy 单文件布局
│   ├── chunks.json
│   └── snapshots/
│       ├── <token>.faiss.index
│       └── <token>.chunks.json
├── model_cache/
│   ├── embeddings/<模型末段名>/            # sentence-transformers 权重
│   └── mineru/
│       └── modelscope/                    # MinerU 本地模型缓存
├── mineru.json                            # 每次本地解析前重写
└── scipal.db                              # 仅当显式设置 SCIPAL_DATA_DIR 时落在这里
```

路径解析优先级：

| 目标 | 顺序 |
|---|---|
| 数据根 | `SCIPAL_DATA_DIR` → `backend/data` |
| 模型缓存 | `SCIPAL_MODEL_DIR` → `<数据根>/model_cache` |
| 数据库 | `SCIPAL_DB_PATH` → `<数据根>/scipal.db` → `backend/src/backend/storage/sqlite/scipal.db` |

> 最后一级回退会把 DB 写进源码包目录，仅适合未配置任何路径的本地开发；生产请显式设置 `SCIPAL_DB_PATH` 或 `SCIPAL_DATA_DIR`。

`backend/src/backend/scripts/migrate_storage.py` 提供旧布局迁移：把 `data/uploads/sessions/<sid>/{documents,parsed,indexes}` 平移到 `backend/data/{raw,parsed,index}/<sid>`；同名冲突且内容不同会 `raise RuntimeError("Storage migration conflict")`。

## 6. 向量库注册表与缓存

`backend/src/backend/application/store_cache.py`

进程内 LRU：`OrderedDict[session_id] = (cache_key, store)`，容量 16，`threading.RLock` 保护。

解析优先级：

1. `retrieval_indexes.status == 'ready'` → 加载该路径，缓存键 `legacy:<updated_at>`。
2. 否则取 active ready 快照 → 缓存键 `snapshot:<id>:<updated_at>`。
3. 无快照但 `chunks` 非空且无处理中文档 → 在内存中重建 store（不落盘）。
4. 否则返回空 store（键 `empty`）。

`discard_store(session_id)` 在快照提交成功、会话删除时调用。

FAISS 落盘格式（`rag/indexing/vector_store.py`）：

- `<token>.faiss.index`：`faiss.write_index` 二进制。
- `<token>.chunks.json`：`[chunk.model_dump()]`，**不含向量**。
- 写入用 `.tmp` + `os.replace`，近似原子。
- 加载时 `index.ntotal != len(chunks)` 只告警不报错；向量与 chunk 的对应完全依赖插入顺序下标。

## 7. 快照回收

每次摄取成功都会把上一份 `ready` 快照打成 `stale`（用于回滚），应用不会自动删除，索引文件会随重建次数线性增长。回收由脚本完成：

```bash
# dry-run：只统计，不删除
uv run --project backend python -m backend.scripts.gc_index_snapshots
# 实际删除 failed 快照与 7 天前的 stale 快照
uv run --project backend python -m backend.scripts.gc_index_snapshots --apply --stale-days 7
```

规则（`backend/src/backend/scripts/gc_index_snapshots.py`）：

- 候选集合 = 全部 `failed` + `updated_at` 早于 `--stale-days`（默认 7）的 `stale`；`ready` / `building` **永不被选中**。
- 文件路径必须位于 `<data>/index` 内，否则跳过并告警（防误删）。
- `--apply` 时先删文件、再删行；不加 `--apply` 仅统计。
- 仓储支撑：`index_snapshots.list_snapshots_pending_cleanup` / `delete_snapshot`。
- 建议在没有摄取任务运行时执行——提交失败的回滚依赖上一份 `stale` 文件。

## 8. 迁移历史

`init_db()` 用 `PRAGMA user_version` 判断：

| 版本 | 变更 |
|---|---|
| v1（新库） | 直接创建当前全量 schema 并置 `user_version = 5` |
| v2 | `chunks(document_id, chunk_index)` 唯一索引 |
| v3 | `retrieval_indexes.created_at` 补列并回填；新增 `idx_sessions_list` 部分索引 |
| v4 | 重建 6 张含外键表，补全 `ON DELETE CASCADE` / `SET NULL` |
| v5 | 新增 `users` 表 |

新库不执行增量脚本，只有旧库才逐版本升级；升级过程 `PRAGMA foreign_keys = OFF` → 重建表 → 重建索引 → `ON`，异常自动 rollback。

新增表/列时的推荐做法：

1. 在 `schema.py` 的 `_create_schema` 里加入最新 DDL（新库路径）。
2. 把 `CURRENT_SCHEMA_VERSION` +1，在 `_migrate_schema` 里加对应分支（旧库路径）。
3. 在对应仓储模块补函数，并在 `storage/sqlite/__init__.py` 导出。
