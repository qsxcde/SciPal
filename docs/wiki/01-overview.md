# 01 项目概览

## 1. 定位

SciPal 是一个**单会话内、面向学术论文阅读的 RAG 问答系统**：用户上传 PDF 后，系统在后台完成解析与索引，然后基于论文内容用中文流式作答，并附带来源片段。

设计上强调三件事：

- **异步可观测**：上传立即返回 `202`，文档状态、任务状态、会话状态都可查询。
- **索引原子提交**：检索索引以不可变快照发布，构建失败不污染已可用索引。
- **回答可追溯**：回答必须给出 `[Section: 章节]` 引用，服务端还会与检索到的章节集合做校验。

## 2. 能力边界

| 支持 | 不支持 / 未实现 |
|---|---|
| 文本型 PDF 解析（MinerU 云 API / MinerU 本地 / pypdf 三级降级） | 扫描版、纯图片型 PDF |
| 单会话内多文档累积索引 | 跨会话联合检索 |
| BM25 + Dense 混合检索、RRF 融合、重排序 | 任意规模的 ANN 索引（当前为 `IndexFlatL2` 精确检索） |
| 中文回答 + `SourceRef` 来源引用 | 多轮对话的独立改写模型（依赖规则 + LLM 辅助） |
| DeepSeek 主模型 + GLM/Qwen/Ollama 降级 | 未配置 `DEEPSEEK_API_KEY` 时无法生成 |
| PC Web 前端 | 移动端适配 |
| 离线检索/生成评测 CLI | 在线 A/B、流量灰度 |

## 3. 技术栈

| 层 | 选型 | 说明 |
|---|---|---|
| 前端 | Vue 3 + TypeScript + Element Plus + Vite 8 | 手写 `composables`，无 Pinia/Vuex |
| 后端 API | FastAPI + Pydantic v2 + pydantic-settings | 单进程，无 celery/redis |
| 异步任务 | `InProcessJobRunner`（daemon 线程） | FIFO + 会话级串行锁 |
| PDF 解析 | MinerU（云 API / 本地 CLI）+ pypdf | 顺序降级 |
| Embedding | sentence-transformers（本地）/ OpenAI 兼容远程 API | 远程优先（配置了 key 时） |
| 向量检索 | FAISS `IndexFlatL2` | 精确 L2，`normalize_embeddings=True` 时等价余弦 |
| 关键词检索 | 自实现 BM25（中英混合分词） | 无外部依赖 |
| Rerank | 远程 `/rerank` API → 本地 cross-encoder → 原序截断 | 三级降级 |
| LLM | OpenAI Python SDK，DeepSeek 主用 | GLM/Qwen/Ollama 可选降级 |
| 持久化 | SQLite（WAL）+ 本地文件目录 | 无外部数据库 |
| 测试 | pytest（`asyncio_mode=auto`） | 标记 `unit` / `integration` / `import_isolation` / `slow` |

## 4. 端到端主流程

### 4.1 上传（同步部分，毫秒级）

```
POST /sessions/{id}/documents  (multipart, field=file)
  ├── 校验：会话存在、大小为 0 < n ≤ 50MiB、魔数 %PDF
  ├── 写盘：<data>/raw/<session_id>/<document_id>.pdf
  ├── documents 行：status = uploaded, chunk_count = 0
  ├── jobs 行：type = document_ingestion, status = queued, stage = uploaded
  ├── 若会话标题仍是默认值 → 改为文件名
  └── 202 {document_id, job_id, document_status, job_status, session_status}
```

### 4.2 摄取（后台，秒~分钟级）

```
InProcessJobRunner.tick (每 runner_idle_poll_interval=0.05s 轮询)
  └── 取 1 条 status=queued 的 job（created_at 升序）
        ├── mark_job_running (CAS, attempt+1)
        ├── 加会话级锁，串行执行
        └── worker.handlers.ingest_document → application.ingestion.run_document_ingestion_job
              parsing → rag.ingestion.pipeline.process_pdf_document
              parsed   → 写 4 个产物文件 + 回写文档元数据
              chunked  → 覆盖 chunks 表
              indexing → 建候选 FAISS 快照 → 提交为 ready
              ready    → 文档状态 ready，旧快照转 stale
```

### 4.3 问答（SSE，首 token 秒级）

```
POST /sessions/{id}/messages  {role: "user", content: "..."}
  ├── 无 ready 快照 → 轮询等待（0.05s 退避至 1.0s，总预算 10s）
  ├── 持久化 user message
  ├── 检索：历史改写 → 术语扩展 → BM25 + Dense → RRF → Rerank → 上下文扩展
  ├── 生成：DeepSeek 流式 → 失败降级到 fallback / Ollama
  └── SSE: status → token* → [warning] → sources → done
         （assistant message 在 done 前落库）
```

## 5. 仓库结构

```
SciPal/
├── README.md                     # 面向使用者的快速上手
├── pytest.ini                    # pytest 标记注册（unit/integration/import_isolation/slow）
├── backend/
│   ├── pyproject.toml            # 包名 scipal-backend，含 dev / eval 依赖组
│   └── src/
│       ├── backend/
│       │   ├── main.py           # 装配根：CORS、异常映射、router、job runner
│       │   ├── config.py         # RuntimeSettings + 路径函数 + settings 单例
│       │   ├── api/              # 传输层：routes / schemas / deps / errors / streaming / security
│       │   ├── application/      # 用例层：sessions / documents / ingestion / indexing / chat / evaluation
│       │   ├── domain/           # 领域模型、状态枚举、授权规则、异常
│       │   ├── rag/              # ingestion / indexing / retrieval / generation / embedding / answer
│       │   ├── storage/          # paths + sqlite 仓储
│       │   ├── worker/           # runner（handler 注册表）+ handlers（job → 用例）
│       │   ├── prompts/          # prompts.toml（回答/改写/术语扩展）
│       │   └── scripts/          # 旧数据目录迁移脚本
│       └── scipal_eval/          # 离线评测 CLI（检索/生成/RAGAS/Judge）
├── frontend/
│   ├── src/                      # Vue 3 应用（views / components / composables / api.ts）
│   └── prototypes/               # 静态 HTML 设计稿，不参与构建
├── openspec/                     # spec-driven change 归档（当前无 specs/）
└── docs/wiki/                    # 本 Wiki
```

各层职责与依赖方向见 [02 系统架构](02-architecture.md)；数据落盘位置见 [03 数据模型与存储](03-data-model.md)。

## 6. 运行形态

- **单进程**：一个 uvicorn 进程同时承载 API 与后台任务线程；不依赖 broker，重启后由启动恢复逻辑回收在途 job。
- **两个并发面**：asyncio 事件循环处理 HTTP/SSE，耗时 I/O 通过 `asyncio.to_thread` 或 `run_in_executor` 下放；job runner 独占一个 daemon 线程。
- **状态三处存储**：SQLite（权威元数据）、本地文件（PDF / 解析产物 / FAISS 快照）、进程内缓存（向量库 LRU，容量 16）。
- **一致性策略**：先写文件再提交元数据；索引"先建候选、后原子提升"，失败时回滚到上一 ready 快照。

## 7. 与 README 的差异提示

仓库根 `README.md` 是面向使用者的入口文档，存在少量与当前代码不一致之处，阅读时以本 Wiki 为准：

- README 示例配置中的 `EMBEDDING_MODEL=Qwen/Qwen3-Embedding-0.6B` 与代码默认值 `BAAI/bge-small-en-v1.5` 不同，默认值以 [08 配置参考](08-configuration.md) 为准。
