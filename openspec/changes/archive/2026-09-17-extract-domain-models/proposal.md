## Why

`Chunk` / `ChunkMetadata` / `SourceRef` 是全系统跨层共享的领域模型，被 **4 层、20 个源文件**依赖。但它住在 `rag/ingestion/metadata.py`——而 `rag/retrieval` 是它的最大消费者（8 个文件），远超名义上的归属地 `rag/ingestion`（2 个文件）。

这带来两个具体代价：

1. **层次倒置**：`storage/sqlite/chunks.py:4` 与 `storage/sqlite/messages.py:5` 必须反向 import `rag` 才能读写自己的数据。这是当前项目中唯一的反向依赖（`rag` 对 `storage` 的依赖为 **0**），根因就是领域模型的类型定义放错了层。
2. **命名误导**：`from backend.rag.ingestion.metadata import Chunk` 会让读者以为 `Chunk` 是 ingestion 的内部概念，而它实际是整个系统的通用语言——检索返回它、生成消费它、存储序列化它、HTTP 契约暴露它。

本变更是唯一**零风险、不依赖测试、且解锁后续全部 `rag` 层重组**的动作：领域模型归位后，`rag` 内部如何重组都不再牵动 `storage`。

## What Changes

- **移动** `rag/ingestion/metadata.py` → `domain/models.py`；`ChunkMetadata` / `Chunk` / `SourceRef` 三个模型原样搬迁，字段定义与语义不变
- **更新** 20 个源文件的 import 路径
- **更新** `domain/__init__.py` 的 `__all__`，纳入 `models`
- **复核** 文档与注释中的路径引用

明确不变：三个模型的字段与语义、全部运行时行为、HTTP 端点与请求/响应格式、SSE 事件序列、数据库 schema、数据目录布局。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。

本变更为纯位移（模块重定位），不改变任何 spec 级行为——模块的内部导入路径属于实现细节，不属于系统行为。因此按 schema 约定在 `.openspec.yaml` 中标记 `skip_specs: true`，不产出 delta spec。

## Impact

**受影响代码**：20 个源文件（跨 4 层）+ `domain/__init__.py`

| 层 | 文件数 | 具体文件 |
|---|---|---|
| `domain` | — | 新增 `models.py`（搬迁目标） |
| `rag/retrieval` | 8 | `bm25`、`context_builder`、`filters`、`fusion`、`hybrid_retriever`、`remote_reranker`、`reranker`、`retriever` |
| `app` | 3 | `contracts.py`、`services/chat_service.py`、`services/ingestion_service.py` |
| `rag/ingestion` | 2 | `chunking`、`pipeline` |
| `rag/generation` | 2 | `answer_generator`、`prompt_template` |
| `storage/sqlite` | 2 | `chunks`、`messages` |
| `rag/indexing` | 1 | `vector_store` |
| `rag/pipeline` | 1 | `online_pipeline` |
| `scipal_eval` | 1 | `draft_generator` |

**解除的依赖**：`storage → rag` 的 4 处反向依赖中解除 **2 处**（`chunks.py`、`messages.py`）。剩余 2 处在 `storage/vector_db/registry.py:6-7`（依赖 `rag.indexing.vector_store` 与 `rag.retrieval.filters`），涉及"向量库归属哪一层"的架构决策，本变更不处理。

**不受影响**：HTTP 端点集合与路径、请求/响应格式、数据库 schema、数据目录、`pyproject.toml` 入口点、README 启动命令。

**验证方式**：全模块遍历导入（基线 91，期望仍为 91）+ `app.openapi()` 路由清单比对（基线 8 条）+ `uv build` + 旧路径全仓扫描。

**与他变更的关系**：本变更是后续工作的前置位移——`rag` 层重组（`index_service` 迁入 `rag/indexing`、`pipeline/` 并入 `generation/`、`ingestion/` 三分）与依赖重构（拆 `chat_service`、下沉 SSE 事件）都涉及 `rag` 内部搬迁，若领域模型仍在 `rag` 内，每次搬迁都会连带牵动 `storage`。本变更本身不依赖测试网，可独立交付与回滚。
