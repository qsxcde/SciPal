## Context

参见 `proposal.md` 的 Why 一节了解动机。本节只记录塑造实现方式的当前状态与约束。

**当前状态**

- `rag/ingestion/metadata.py` 共 37 行，定义三个 Pydantic 模型：`ChunkMetadata`、`Chunk`、`SourceRef`
- 被 20 个源文件引用，分布：`rag/retrieval` 8、`app` 3、`rag/ingestion` 2、`rag/generation` 2、`storage/sqlite` 2、`rag/indexing` 1、`rag/pipeline` 1、`scipal_eval` 1
- `backend/domain/` 现有 `config.py` / `states.py` / `exceptions.py`，`__init__.py` 的 `__all__` 列出三者
- `storage → rag` 共 4 处反向依赖，其中 2 处指向本文件（`chunks.py:4`、`messages.py:5`），另 2 处在 `storage/vector_db/registry.py:6-7`
- `rag → storage` 依赖为 0

**约束**

1. **零测试覆盖**：验证必须依靠结构等价性检查，不能依赖回归测试
2. **运行时契约不可变**：HTTP 契约、SSE 事件序列、数据库 schema、数据目录、入口点均不得变动
3. **纯位移**：三个模型的字段定义、校验规则、序列化行为均不修改
4. **`domain/` 必须保持零外部依赖**：它是依赖图的根，不能引入对任何其他层的引用

## Goals / Non-Goals

**Goals**

- 使领域模型位于依赖图根部，消除 `storage → rag` 中由类型定义位置引发的 2 处反向依赖
- 让模块路径能直接表达"这是全系统共享的领域模型"
- 为后续 `rag` 层内部重组消除连带影响——重组 `rag` 时不再牵动 `storage`

**Non-Goals**

- 不处理 `storage/vector_db/registry.py` 的剩余 2 处反向依赖（涉及"向量库归属哪一层"的架构决策，需独立变更）
- 不修改三个模型的任何字段或语义
- 不拆分 `metadata.py` 为多个文件（见 D1）
- 不引入新依赖、不改动 `domain/` 中既有的 `config` / `states` / `exceptions`

## Decisions

### D1 · 目标为单一文件 `domain/models.py`，不拆分

**理由**：三个模型构成一个内聚家族——`Chunk` 持有 `ChunkMetadata`，`SourceRef` 是 `Chunk` 面向引用的投影。合计 37 行，拆开只会增加跳转成本。`models` 虽是通用名，但在 `domain/` 这个只有四个模块的包里足够明确。

**备选**：
- `domain/chunks.py`：更具体，但 `SourceRef` 严格说不属于"chunk"概念
- 拆为 `domain/chunk.py` + `domain/source.py`：37 行拆两个文件属过度设计
- `domain/ir.py`：与 `rag/ingestion/document_ir.py` 概念混淆（那是解析产物 IR，这是检索单元）

### D2 · 模块名 `metadata` → `models`

**理由**：原名描述"元数据"，但文件里只有 `ChunkMetadata` 是元数据；`Chunk` 是实体、`SourceRef` 是引用投影。搬迁是修正名称的最佳时机——留下 `domain/metadata.py` 会把一个不准确的名称固化到依赖图的根部。

**这是本变更中唯一的"顺便改名"**，其余一律保持原样。

**备选**：保持文件名 `metadata.py` 以减少 diff——但改名成本已被 20 处 import 更新覆盖，边际成本为零。

### D3 · 三个模型一起搬迁

**理由**：`SourceRef` 与 `Chunk` 是同一家族（前者是后者的投影），且它同样被跨层使用（`storage/sqlite/messages.py`、`app/contracts.py`）。只搬 `Chunk`/`ChunkMetadata` 会让 `domain/models.py` 与 `rag/ingestion/metadata.py` 同时存在、语义交叉。

### D4 · 一次性全量替换

**理由**：与上一个结构变更同理——纯位移下，逐个模块迁移会产生"新旧路径混用"的中间态，而中间态无法通过任何静态检查。一次性替换后用 V1–V5 一次性收口。

**备选**：先新建 `domain/models.py` 作为转发层、再逐个迁移、最后删除旧文件。这会引入"两个真源"的窗口，且转发层本身需要额外维护，收益不抵成本。

### D5 · 验证加入"目标达成度"检查（V5）

这是本变更与前一个结构变更的**关键差异**：前者的目标是"结构更清晰"，难以机械验证；本变更有**明确的机器可验证指标**——反向依赖数量。

| # | 检查 | 判定标准 |
|---|---|---|
| V1 | 全模块遍历导入 | 91 个模块，0 失败 |
| V2 | `app.openapi()` 路由清单 | 与基线逐条一致（8 条） |
| V3 | `uv build` | sdist + wheel 构建成功 |
| V4 | 旧路径全仓扫描 | 无 `rag.ingestion.metadata` / `rag/ingestion/metadata` 残留 |
| **V5** | **`storage/sqlite/` 对 `rag` 的依赖** | **归零**（本变更的验收标准） |

V5 必须单独设立：如果只跑 V1–V4，一个"搬迁完成但仍有人从 `rag` 转口引用"的实现也能全绿通过，而那样并没有达成变更目的。

## Risks / Trade-offs

| 风险 | 缓解 |
|---|---|
| 【遗漏 import】某文件仍引用旧路径 | V1 立即暴露；V4 字符串扫描兜底（含文档与注释） |
| 【Pydantic 模型内部引用失效】`Chunk.metadata: ChunkMetadata` 是文件内直接引用 | 两者同文件搬迁，引用关系不变；V1 覆盖 |
| 【`scipal_eval` 遗漏】该包在 `src/` 下的另一顶层目录 | 已核查：`draft_generator.py` 1 处引用，纳入 20 个文件清单，V1 覆盖 |
| 【循环导入】新位置引发依赖环 | `domain/models.py` 仅依赖 pydantic，`domain/` 无任何内部层引用，结构上不可能成环；V1 验证 |
| 【`__pycache__` 残留】旧路径的 .pyc 干扰验证 | 迁移前清理一次、验证前再清理一次 |
| 【`domain/` 职责漂移】后续可能有人把业务逻辑塞进 `models.py` | 在模块 docstring 中写明"仅承载跨层共享的数据契约，不含行为" |

**权衡说明**：本变更收益是**依赖图正确性**与**后续重构的可行性**，不是性能或功能。因此验收标准是 V5 的归零结果，而非"代码能跑"。

## Migration Plan

**执行步骤**

1. `git mv backend/src/backend/rag/ingestion/metadata.py backend/src/backend/domain/models.py`
2. 在 `domain/models.py` 顶部补充模块 docstring（说明它是共享数据契约、不含行为）
3. 全量替换 20 个文件的 import：`backend.rag.ingestion.metadata` → `backend.domain.models`
4. 更新 `domain/__init__.py` 的 `__all__`，加入 `"models"`
5. 清理 `__pycache__`
6. 执行 V1–V5 五项验证，全部通过后提交

**提交粒度**：单个提交（纯位移，拆分只会产生不可验证的中间态）。

**回滚策略**：`git revert` 单个提交。无数据库迁移、无配置变更、无数据目录变更。

## Open Questions

- `storage/vector_db/registry.py:6-7` 的剩余 2 处反向依赖如何处理？这需要先决定"向量库与加载策略归属 `rag` 还是 `storage`"——该决策会同时影响 `rag/indexing` 的重组方案，宜与"`rag` 层重组"变更一并决定。
- `domain/models.py` 未来若增长到需要拆分（例如引入更多领域实体），拆分维度按"实体 / 值对象 / 引用投影"还是按业务概念？——当前 37 行无需决定。
