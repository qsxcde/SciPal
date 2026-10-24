# SciPal 项目 Wiki

面向 SciPal 仓库的工程知识库。所有结论均以当前代码为准，正文中标注了对应的源码路径，便于随时回查验证。

- 事实基线：`main` 分支当前工作副本，SQLite schema `user_version = 5`
- 最后核对：2026-10-25
- 覆盖范围：`backend/src/backend`、`backend/src/scipal_eval`、`frontend/src`

## 文档目录

| 文档 | 内容 | 主要读者 |
|---|---|---|
| [01 项目概览](01-overview.md) | 定位、能力边界、技术栈、术语表、端到端主流程、仓库结构 | 所有人 |
| [02 系统架构](02-architecture.md) | 分层、模块职责、启动时序、请求生命周期、并发模型、错误处理 | 后端 |
| [03 数据模型与存储](03-data-model.md) | 8 张表、ER 关系、4 个状态机、磁盘布局、向量库缓存、迁移历史 | 后端 |
| [04 API 参考](04-api.md) | 全部 HTTP 端点、请求/响应字段、SSE 协议、错误码、调用示例 | 前后端 |
| [05 文档摄取与索引](05-ingestion-and-indexing.md) | 上传→解析→归一化→切块→FAISS 快照提交/回滚的完整链路 | 后端 / 算法 |
| [06 检索与问答](06-retrieval-and-chat.md) | 改写、BM25+Dense 混合召回、RRF、重排、上下文、生成与引用校验 | 后端 / 算法 |
| [07 前端](07-frontend.md) | 组件树、composables、SSE 消费、上传轮询、已知问题 | 前端 |
| [08 配置参考](08-configuration.md) | 全部 `RuntimeSettings` 字段、环境变量、路径解析、鉴权开关 | 运维 / 后端 |
| [09 离线评测](09-evaluation.md) | `scipal_eval` CLI、数据集格式、指标、阈值、产物结构 | 算法 / 评测 |
| [10 开发与运维](10-development.md) | 环境搭建、测试约定、常见改动 how-to、排障 FAQ、已知缺口 | 所有人 |

## 推荐阅读路径

- 新人上手：01 → 02 → 04 → 10
- 排查"上传后一直处理中"：05 → 03（状态机）→ 10（FAQ）
- 排查"回答没有依据/引用为空"：06 → 05（`sources` 来源）→ 03（`chunks` 表）
- 改检索效果：06 → 08（参数）→ 09（评测回归）
- 前端联调：04（SSE 协议）→ 07

## 一分钟速览

```
浏览器 (Vue 3 + Element Plus)
   │  REST + SSE (fetch, Bearer JWT)
   ▼
FastAPI (backend.app.main)
   │  路由 → 服务层（模块级函数直调，无 DI 容器）
   ├── SQLite（8 表，WAL，backend/data/scipal.db 或 SCIPAL_DB_PATH）
   ├── 本地文件（raw/ 解析产物 / index/ FAISS 快照）
   ├── InProcessJobRunner（daemon 线程，进程内 FIFO 任务队列）
   └── RAG（MinerU/pypdf 解析 → 切块 → Embedding → FAISS → 混合检索 → LLM 流式生成）
```

三条业务主线：

1. `POST /sessions` → 建会话（无文档时状态为 `empty`）。
2. `POST /sessions/{id}/documents` → 落盘 + 建 `documents` / `jobs` 行 → 立即 `202`；后台线程推进 `uploaded → parsing → parsed → chunked → indexing → ready`。
3. `POST /sessions/{id}/messages` → 等 active ready 快照 → 检索 → LLM 流式生成 → SSE 返回 `token` / `sources` / `done`。

## 术语表

| 术语 | 含义 | 关键位置 |
|---|---|---|
| Session（会话） | 一次论文阅读会话，聚合文档、消息、任务与索引 | `domain/models.py`、`storage/sqlite/sessions.py` |
| Document（文档） | 上传的单个 PDF，状态机见 03 章 | `storage/sqlite/documents.py` |
| Job（任务） | 单次摄取尝试，`attempt` 记录重试次数 | `storage/sqlite/jobs.py` |
| Chunk（分块） | 检索最小单位，正文 + 结构化元数据 | `domain/models.py`、`ingestion/chunking.py` |
| Snapshot（索引快照） | 不可变的"整会话累积索引"，`building → ready`，旧版转 `stale` | `storage/sqlite/index_snapshots.py` |
| DocumentIR | 归一化后的文档中间表示（页 / 块 / 大纲 / 质量报告） | `ingestion/document_ir.py` |
| SourceRef | 回答引用的来源片段（章节、页码、chunk 序号、置信度） | `domain/models.py` |

## 文档约定

- 路径均相对仓库根目录书写（如 `backend/src/backend/app/main.py`）。
- 「默认值」指 `RuntimeSettings` 的字段默认值，可通过同名大写环境变量或仓库根 `.env` 覆盖（详见 08 章）。
- 「已知限制」只描述代码当前行为，不代表计划。
