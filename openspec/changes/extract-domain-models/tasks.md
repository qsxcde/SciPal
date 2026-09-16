## 1. 基线与准备

- [x] 1.1 记录基线：全模块遍历导入的模块总数（预期 91）、`app.openapi()` 的路径清单（预期 8 条）、`storage → rag` 的 4 处依赖清单（供 V5 对比）
- [x] 1.2 清理 `src/` 下全部 `__pycache__`，避免旧路径的 .pyc 干扰验证

## 2. 搬迁领域模型

- [x] 2.1 `git mv backend/src/backend/rag/ingestion/metadata.py backend/src/backend/domain/models.py`（保留文件历史）
- [x] 2.2 在 `domain/models.py` 顶部补充模块 docstring，写明它仅承载跨层共享的数据契约、不含行为

## 3. 更新引用

- [x] 3.1 全量替换 20 个源文件的 import：`backend.rag.ingestion.metadata` → `backend.domain.models`
- [x] 3.2 更新 `domain/__init__.py` 的 `__all__`，加入 `"models"`
- [x] 3.3 更新 `rag/ingestion/__init__.py` 的 `__all__`，移除 `"metadata"`
- [x] 3.4 复核仓库内文档与注释中的路径引用（含 `openspec/` 之外的所有文本文件）

## 4. 验证（V1–V5）

- [x] 4.1 V1 全模块遍历导入：91 个模块，0 失败（与基线一致）
- [x] 4.2 V2 `app.openapi()` 路由清单与 1.1 记录的基线逐条一致（8 条）
- [x] 4.3 V3 `uv build` 成功产出 sdist 与 wheel
- [x] 4.4 V4 全仓扫描确认无 `rag.ingestion.metadata` / `rag/ingestion/metadata` 残留
- [x] 4.5 V5 **验收标准**：`storage/sqlite/` 对 `rag` 的依赖归零 ✓（剩余 2 处在 `storage/vector_db/registry.py`，按 design 非目标保留）

## 5. 收尾

- [x] 5.1 确认 `rag/ingestion/metadata.py` 已不存在，且 `domain/models.py` 中存在 `ChunkMetadata` / `Chunk` / `SourceRef` 三个模型
- [x] 5.2 清理 `__pycache__`，确认工作树无临时验证产物
- [ ] 5.3 以单个提交完成交付（纯位移，拆分只会产生不可验证的中间态；提交动作需用户确认）
