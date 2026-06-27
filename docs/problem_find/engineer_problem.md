# 工程化问题分析报告

> 日期：2026-06-27
> 范围：代码结构、错误处理、线程安全、日志、安全等
> 方法：逐项代码验证，非 AI 推测

---

## 已确认的真实问题

### P1 — 正确性风险

#### 1. 异常被静默吞没，无日志记录

**位置：** `backend/rag/retrieval/query_rewriter.py:76-77`

```python
except Exception:
    return fallback_query_pack(query)
```

当 `generate_query_pack` 中的 LLM 调用、JSON 解析或 `QueryPack.model_validate` 抛出异常时，调用被静默降级为返回原始 query（`fallback_query_pack`）。没有任何日志记录错误原因。

**影响：** 运维完全察觉不到 query rewrite 功能异常。LLM 可用性问题、JSON 格式错误、模型输入异常都会被无声吞没。唯一的表现是检索质量下降，但原因不可追溯。

**修复：** 在 `return` 前加一行 `logger.exception(...)`。

---

#### 2. `init_db()` 中的 _in_progress 标志存在竞态条件

**位置：** `backend/storage/sqlite/schema.py:5-13`

```python
_in_progress = False

def init_db() -> None:
    global _in_progress
    if _in_progress:       # Thread A 和 Thread B 同时读到 False
        return
    _in_progress = True    # 两个线程都设为 True，都进入临界区
```

两个线程同时调用 `init_db()` 时，会同时通过 `_in_progress` 检查，导致：
1. 两个线程各自调用 `connect()` 打开独立连接
2. 两个线程可能在同一个数据库文件上并发执行 `CREATE TABLE IF NOT EXISTS`
3. SQLite 对 DDL 操作有一定保护，但仍存在竞争窗口

**影响：** 低概率但高影响。在 FastAPI 的多个 worker 或线程池中，如果多个请求在数据库初始化完成前同时到达，可能触发。

**修复：** 将 `_in_progress` 替换为 `threading.Lock`。

---

### P2 — 线程安全性（中等风险）

#### 3. FAISS 存储注册表 `_stores` 缺少锁保护

**位置：** `backend/storage/vector_db/registry.py:15-79`

```python
_stores: OrderedDict = OrderedDict()
_store_lock = threading.Lock()

def get_store(session_id: str) -> FAISSVectorStore:
    cached = _stores.get(session_id)  # 无锁
    ...

def get_store_for_snapshot(snapshot: dict) -> FAISSVectorStore:
    with _store_lock:
        cached = _stores.get(session_id)  # 有锁
```

`get_store()`、`_cache_store()`、`discard_store()`、`clear_cache()` 都直接读写 `_stores` 而没有同步。只有 `get_store_for_snapshot()` 正确地使用了 `_store_lock`。

**影响：** 多线程并发访问时（FastAPI 线程池 + job runner 后台线程），`OrderedDict` 的 `move_to_end` / `popitem` / `get` 操作可能相互冲突，导致 `KeyError`、`ValueError` 或数据不一致。

**修复：** 在 `get_store()` 的缓存检查/写入路径添加 `with _store_lock:`。

---

#### 4. BM25 检索器缓存无锁

**位置：** `backend/rag/retrieval/hybrid_retriever.py:18, 32, 36`

```python
_bm25_cache: dict[str, tuple[str, BM25Retriever]] = {}

def _get_bm25_retriever(chunks: list[Chunk]) -> BM25Retriever:
    cached = _bm25_cache.get("default")  # 无锁
    ...
    _bm25_cache["default"] = (fp, retriever)  # 无锁
```

`_get_bm25_retriever` 在 `retrieve_hybrid_context` 中被调用，后者通过 `chat_service.py` 的 `_to_thread` 在多个线程中运行。

**影响：** 多线程并发对 dict 的写入可能导致缓存读取到不完整的 `(fp, retriever)` 元组或丢失更新。

**修复：** 加 `threading.Lock` 保护或使用 `functools.lru_cache(maxsize=1)`。

---

### P3 — 代码质量

#### 5. 函数体内 `import re`

**位置：** `backend/rag/retrieval/query_rewriter.py:56`

```python
def _strip_markdown_fence(text: str) -> str:
    import re  # 应该放在文件顶部
```

每次 `generate_query_pack` 调用都会触发一次函数内的 `import re`。虽然 Python 的 `sys.modules` 缓存使其开销很小（仅 dict 查找），但这不是标准做法，且会让代码审查者困惑。

**修复：** 将 `import re` 移到文件顶部。

---

#### 6. 未使用的函数参数

**位置：** `backend/app/services/index_service.py:18-20`

```python
def build_candidate_snapshot(session_id: str, document_id: str, pdf_bytes: bytes) -> dict:
    _ = pdf_bytes
```

`pdf_bytes` 参数被立即丢弃。这是一个设计遗留物——以前这个函数需要 PDF bytes 来构建索引，现在数据从 SQLite 加载。调用方（`ingestion_service.py:116`）仍然传递这个值，但接收方完全不使用它。

**影响：** 代码误读风险。未来的开发者可能以为 `pdf_bytes` 被使用了。

**修复：** 从函数签名中移除 `pdf_bytes`，同时更新调用方。但需确认调用链中的所有中间函数不依赖此接口。

---

### P4 — 运维

#### 7. 无集中日志配置

**位置：** 全局

整个 `backend/` 下没有任何 `logging.basicConfig`、`dictConfig`、`fileConfig` 调用。日志输出格式和级别完全依赖 uvicorn 的默认配置。

**影响：**
- 如果 SciPal 被嵌入其他应用或作为脚本运行，日志不会自动输出
- 无法统一控制日志级别（如 `DEBUG` 模式）
- 没有 request ID 等结构化字段

**修复：** 在 `app/main.py` 的 lifespan 中添加 `logging.basicConfig` 或 `dictConfig`。

---

#### 8. `asyncio.run()` 在不安全的同步函数中使用

**位置：** `backend/evals/cli.py:214, 243`

```python
return asyncio.run(evaluate_session_chat(...))
```

在同步函数 `_evaluate_with_scipal` 和 `_evaluate_retrieval_only` 中直接使用 `asyncio.run()`。如果从 FastAPI 异步请求处理链中调用这些函数（例如通过未来某个 Web 触发评估的功能），会抛出 `RuntimeError: asyncio.run() cannot be called from a running event loop`。

**影响：** 目前 eval CLI 只从命令行调用（`if __name__ == "__main__"`），所以不会触发此问题。但如果 eval 功能被 Web API 复用则立即崩溃。

**修复：** 添加事件循环存在性检查，或重构为纯异步。

---

## Agent 报告的错误结论

以下为上一轮审计报告中记录的、但经核实不成立的问题：

| Agent 声称 | 实际结论 |
|-----------|---------|
| `.env` 被 git 跟踪 | `.env` 在 `.gitignore` 第 4 行，不被 Git 跟踪 |
| 版本锁定过松 (ragas/langchain) | `>=0.3.0,<1.0.0` 是合理的版本范围，非工程问题 |
| 缺少 E2E 测试 | 有集成测试覆盖关键路径，但确实没有一次走通完整上传→问答链路的测试。部分事实但严重程度被夸大 |

---

## 未发现问题的审查项

以下工程领域经审查后没有发现问题：

| 领域 | 结论 |
|------|------|
| SQL 注入 | 所有查询使用 `?` 参数化占位符，包括 `executemany` |
| 路径穿越 | `storage/paths.py` 的 `remove_session_dir` 使用 `is_relative_to` 验证路径范围 |
| 临时文件安全 | 使用 `TemporaryDirectory`（上下文管理器）、原子写入（`os.replace`） |
| 敏感信息泄露 | API Key 等不记录在日志输出中 |
| 时区处理 | 全部使用 `UTC.isoformat()`，无 naive datetime |
| Python 类型注解 | 主要函数和参数都有类型注解 |
| 资源泄露 | 所有 `TemporaryDirectory`、文件连接使用 `try/finally` 或上下文管理器 |
