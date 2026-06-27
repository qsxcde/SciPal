# 工程化问题修复计划

> 日期：2026-06-27
> 基于：`docs/problem_find/engineer_problem.md`
> 优先级：P1 → P2 → P3 → P4

---

## Task 1: query_rewriter.py 异常日志 + import re

**文件：** `backend/rag/retrieval/query_rewriter.py`

**步骤：**
1. 在 `generate_query_pack` 的 `except Exception` 中添加 `logger.exception()`
2. 将 `_strip_markdown_fence` 内部的 `import re` 提到文件顶部

**风险：** 无。仅增加日志、移动导入位置。

---

## Task 2: schema.py `_in_progress` 竞态修复

**文件：** `backend/storage/sqlite/schema.py`

**步骤：**
1. 将 `_in_progress: bool` 替换为 `_init_lock: threading.RLock`
2. `init_db()` 入口处 `with _init_lock:`
3. 移除 `global _in_progress`

**风险：** 低。`_in_progress` 仅用作递归保护标志，替换为锁后语义完全等价且线程安全。

---

## Task 3: registry.py `_stores` 无锁修复

**文件：** `backend/storage/vector_db/registry.py`

**步骤：**
1. 将 `_store_lock = threading.Lock()` 改为 `threading.RLock()`
2. 在 `get_store()` 的缓存检查/写入路径添加 `with _store_lock:`
3. 在 `discard_store()` 和 `clear_cache()` 中添加 `with _store_lock:`

**风险：** 需用 `RLock` 而非 `Lock`，因为 `get_store()` 会在持有锁时调用 `get_store_for_snapshot()`，后者也会获取同一把锁。

---

## Task 4: hybrid_retriever.py BM25 缓存无锁修复

**文件：** `backend/rag/retrieval/hybrid_retriever.py`

**步骤：**
1. 新增 `_bm25_cache_lock = threading.Lock()`
2. `_get_bm25_retriever` 中对缓存的读写加锁

**风险：** 无。

---

## Task 5: index_service.py 未使用的参数清理

**文件：** `backend/app/services/index_service.py`、`backend/app/services/ingestion_service.py`

**步骤：**
1. 从 `build_candidate_snapshot` 签名中移除 `pdf_bytes: bytes`
2. 从函数体中移除 `_ = pdf_bytes`
3. 更新 `ingestion_service.py` 中的调用方，移除 `pdf_bytes` 实参

**风险：** 中等。确认 `build_candidate_snapshot` 没有其他调用方传递 `pdf_bytes`。需 grep 所有引用。

---

## Task 6: 集中日志配置

**文件：** `backend/app/main.py`

**步骤：**
1. 在 `lifespan` 中添加 `logging.basicConfig(level=logging.INFO, format=...)`

**风险：** 无。uvicorn 已有默认配置，加 basicConfig 只是兜底。

---

## Task 7: evals/cli.py `asyncio.run()` 安全修复

**文件：** `backend/evals/cli.py`

**步骤：**
1. 在 `asyncio.run()` 调用前添加事件循环存在性检查

**风险：** 低。当前只从 CLI 调用，添加 guard 仅防御未来误用。
