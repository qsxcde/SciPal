# 06 检索与问答

覆盖从"用户提问"到"SSE 返回带引用回答"的完整链路。相关代码：

- 编排：`backend/src/backend/app/services/chat_service.py`、`backend/src/backend/rag/pipeline/online_pipeline.py`
- 检索：`backend/src/backend/rag/retrieval/`
- 生成：`backend/src/backend/rag/generation/`
- 提示词：`backend/src/backend/prompts/prompts.toml`

## 1. 整体链路

生产路径由 `chat_service.production_retrieval_options()` 固定为 `strategy="hybrid"`。

```
用户 query
  │
  ├─(1) 历史改写 history_aware_rewrite            [history_rewrite_enabled=True, max_rounds=4]
  │      触发条件：有历史 且（含指代词 或 查询长度 < 3）
  ├─(2) 术语扩展 term_expand                      [term_expand_enabled=True]
  │      阶段 1：本地词表；阶段 2：LLM 补全缩写
  ├─(3) 跨语言改写 generate_query_pack            [仅当 query 语言 != 文档语言]
  │      → dense_query = retrieval_query
  │      → bm25_query  = translated_query + keywords (+ extra_keywords)
  ├─(4) 双路召回
  │      ├─ BM25  : BM25Retriever(k1=1.5, b=0.75).search(bm25_query, k=8)
  │      └─ Dense : FAISS IndexFlatL2.search_with_ranks(dense_query, k=8)
  ├─(5) RRF 融合 (k=60) → seed_top_k=8
  ├─(6) 重排：远程 /rerank → 本地 cross-encoder → 原序截断   [rerank_top_k=8]
  ├─(7) 过滤参考文献块
  └─(8) 上下文扩展 → 8 块 → 按 (paper_id, page_start, chunk_index) 排序
         │
         ▼
    提示词拼装 → LLM 流式生成 → 引用校验 → sources
```

## 2. 检索各环节

### 2.1 历史改写（`history_rewriter.py`）

- 触发：`history` 非空，且命中中/英指代词表，或 `len(query) < history_rewrite_min_query_length(3)`。
- 只取最近 `history_rewrite_max_rounds(4)` 轮。
- LLM 返回纯文本改写结果；异常/超时静默回退原 query。
- 结果 `lru_cache(128)`。

### 2.2 术语扩展（`term_expander.py`）

- 阶段 1：读取 `term_expand_glossary_path`（默认 `backend/data/term_glossary.json`）做静态映射。
- 阶段 2：满足"启用了 LLM fallback"且（长度 > 5 且 0 词表命中，或含未收录大写缩写）时调 LLM。
- LLM 输出 `{"terms": [{"original": "...", "expansions": [...]}]}`；异常静默跳过。
- 结果 `lru_cache(64)`。

### 2.3 语言判定与跨语言改写

- `language.py`：比较汉字与拉丁字符数量，平手 → `unknown`；少数派占比 ≥ 0.2 记 `is_mixed`。
- query 语言与文档语言不同才触发 `query_rewriter.generate_query_pack`。
- 提示词要求返回 `{"translated_query", "retrieval_query", "keywords"}`；解析或校验失败回退 `fallback_query_pack`（原样查询）。

### 2.4 BM25（`bm25.py`，自实现）

- IDF：`ln(1 + (N - df + 0.5) / (df + 0.5))`。
- 分词：小写正则英文/数字 + 中文单字 + 双字 bigram。
- 参数 `k1=1.5`、`b=0.75`。
- 结果按 `(paper_id, chunk_index)` 去重。
- 索引缓存以 chunk 指纹（`md5(paper_id:chunk_index:section...)`）为键，`store.list_chunks()` 变更时重建。

### 2.5 Dense（FAISS）

- `IndexFlatL2` 精确最近邻，`search_with_ranks` 返回 `(rank, chunk)`；score 为 L2 距离。
- `dense_top_k=0` 可关闭 dense 分支（纯 BM25）。
- embedding 对本地模型做 L2 归一化，因此 L2 距离排序等价余弦相似度。

### 2.6 RRF 融合（`fusion.py`）

```
score(chunk) = Σ_over_routes 1 / (rrf_k + rank_route(chunk))
```

- `rrf_k=60`，两路等权，**不使用 dense 距离绝对值**。
- 同一 chunk 在一路内取最好 rank。
- 同分时按 `(paper_id, chunk_index)` 排序，保证确定性。

### 2.7 重排（`reranker.py` / `remote_reranker.py`）

三级降级：

1. 远程：`reranker_remote_enabled=True` 且配置了 `EMBEDDING_REMOTE_API_KEY` → `POST {base_url}/rerank`，`top_n=top_k`，httpx 超时 30s。
2. 本地：`AutoModelForSequenceClassification` + `trust_remote_code`，`max_length=1024`，`num_labels=1` 取 squeeze，否则取末维。
3. 兜底：`chunks[:top_k]`。

`reranker_enabled=False` 时整段跳过。

### 2.8 过滤（`filters.py`）

`is_reference` 为真，或 `section` / `section_path` 命中参考文献名（含中/德/西/韩文变体，去前导编号）→ 剔除。召回前与上下文扩展前各执行一次。

### 2.9 上下文扩展（`context_builder.py`）

优先级：

1. `seed`：重排后的前 `top_k`，全选。
2. `linked_blocks`：`block_ids ∩ linked_block_ids`（`include_linked_blocks=False` 时默认不带入）。
3. `same_section`：同 `section_path` 且 `|Δchunk_index| ≤ same_section_window(1)`。
4. `adjacent`：仅 `|Δchunk_index| ≤ adjacent_window(1)`。

上限为 `max_expanded_chunks(8)` **按块数**，不是 token 预算。全链路**没有任何** token/字符预算控制；`source_excerpt_max_chars(220)` 只影响 `SourceRef.text_excerpt`，不影响送入 LLM 的正文。

最终按 `(paper_id, page_start, chunk_index)` 排序，保证提示词顺序稳定。

## 3. 参数默认值对照（易踩坑）

`HybridRetrievalOptions` 的 dataclass 默认值、`RetrievalOptions` 的默认值、以及生产环境 `settings` 三者不一致：

| 参数 | `HybridRetrievalOptions` | `RetrievalOptions` | `settings`（生产实际） |
|---|---|---|---|
| `bm25_top_k` | 5 | 5 | **8** |
| `dense_top_k` | 5 | 5 | **8** |
| `seed_top_k` | 5 | 5 | **8** |
| `same_section_window` | **0** | 1 | 1 |
| `include_linked_blocks` | False | **True** | False |
| `strategy` | — | **dense** | hybrid |
| `retrieval_top_k` | — | 5 | 5 |

线上对话永远走 `production_retrieval_options()`，因此以最右列为准；评测可直接构造 `RetrievalOptions` 覆盖。纯 dense 分支（`strategy="dense"`）走 `retrieve_seed_chunks` + `expand_context`，无 RRF、无重排。

## 4. 生成

### 4.1 模型优先级（`generation/model_client.py`）

| 优先级 | provider | 启用条件 | 默认模型 |
|---|---|---|---|
| 1 | `deepseek` | 恒存在（缺 key 时惰性初始化报错） | `deepseek-v4-flash` @ `https://api.deepseek.com` |
| 10 | `fallback`（GLM/Qwen 等 OpenAI 兼容） | `LLM_FALLBACK_ENABLED=True` 且 `FALLBACK_BASE_URL` 非空 | `glm-4-flash` |
| 20 | `ollama` | `LLM_FALLBACK_ENABLED=True` 且 `OLLAMA_BASE_URL` 非空 | `qwen2.5:7b` |

- 单 provider 超时 60s；OpenAI 客户端按 `base_url|api_key` 复用。
- `complete`：`stream=False, temperature=0`；无 `choices` 或 `content is None` 视为失败并降级。
- `stream`：按 provider 顺序**整轮重试**；全部失败抛 `RuntimeError("All N LLM providers failed: ...")`。
- 已知副作用：流式下若某 provider 已 yield 部分 token 后失败，切换 provider 会重跑整段，客户端可能看到重复前缀。

### 4.2 提示词拼装（`prompt_template.build_prompt`）

单条 user message：

```
{SYSTEM_PROMPT}

论文片段:
[Section: A > B | Page: 3-4 | Chunk: 12 | Low confidence source]
<chunk text>

---

[...下一块]

用户问题: {question}

请用中文作答。
```

- 块间分隔 `"\n\n---\n\n"`；头部包含 `Section`、`Page`（单页/区间/缺省不写）、`Chunk`，`confidence < 0.5` 时追加 `Low confidence source`。
- `[rag_answer].system` 的四条约束：中文作答；关键结论标 `[Section: 章节名]`；片段不足直接说"当前片段中没有相关信息"；准确优先。
- 同一 TOML 还托管 `[query_rewrite]`、`[history_rewrite]`、`[term_expand]`，均通过 `importlib.resources.files("backend.prompts")` 以 `tomllib` 读取，读取失败时使用代码内硬编码兜底文本。

### 4.3 `sources` 语义

`build_sources` 对**每个进入提示词的 chunk** 生成一条 `SourceRef`：

```python
SourceRef(
    paper_id=..., section=..., chunk_index=...,
    text_excerpt=text[:220], page_start=..., page_end=...,
    block_ids=..., confidence=...,
)
```

因此 `sources == prompt_chunks`（最多 8 条），与"模型实际引用了哪些片段"无关。

### 4.4 引用校验

- 流式：缓冲全文，用正则 `\[Section:\s*(.+?)\]` 提取引用，若引用的章节集合不是检索到章节集合的子集，追加 `warning=msg_no_valid_citations`（回答保留）。
- 非流式（评测用 `evaluate_answer`）：校验失败**整段丢弃**，替换为 `msg_empty_retrieval`。

## 5. SSE 时序与异常

### 5.1 正常

```
status:waiting_for_index   （仅当首轮无 ready 快照；事件延迟到索引就绪后发出）
status:retrieving
status:generating
token × N
[warning]
sources
done
```

`waiting_for_index` 采用延迟发送：等待回调先写入待发队列，索引就绪后才真正 yield，避免客户端先看到"等待"再看到"检索"的突兀顺序。

### 5.2 异常

| 场景 | 行为 |
|---|---|
| `index_max_wait` 超时 | `status:waiting_for_index` → `token`（`msg_index_not_ready`）→ `sources:[]` → `done`；assistant 以 `failed` 落库 |
| 检索为空 | `token`（`msg_empty_retrieval`）→ `sources:[]` → `done`；`generation_mode="skipped"` |
| 生成异常 | 已生成内容以 `failed` 落库，发 `error("生成失败，请重试。")` + `done` |
| 流协议错误（token 与 dict 事件混用、缺 `sources`） | `RuntimeError` → 走生成异常分支 |
| 客户端断开 | `asyncio.CancelledError`，仅记日志 |
| 路由层未捕获异常 | `error:"internal_error"` + `done`，HTTP 仍 200 |

## 6. 索引等待

`chat_service._wait_for_ready_index`：

- 轮询 `get_active_ready_snapshot`，间隔从 `index_poll_interval(0.05s)` 指数退避到 `index_poll_max_interval(1.0s)`。
- 总预算 `index_max_wait(10s)`，超时抛 `ActiveIndexNotReadyError`。

后台摄取是串行的，多文档场景下后续文档索引时间可能超过 10s，此时用户会收到"论文仍在处理中"提示。

## 7. 已知限制

1. **上下文无 token 预算**：只按块数限制（8 块），长表格/长段落可能撑大 prompt。
2. **RRF 忽略稠密距离**，只使用排名；不同 embedding 模型间的距离不可比。
3. **`sources` 与模型引用解耦**：即使模型没引用某个片段，它仍会出现在 `sources` 中。
4. **流式降级重复前缀**：provider 中途失败后整轮重跑。
5. **参考文献过滤是全量扫描**：`retrieve_hybrid_context` 会对 `store.list_chunks()` 全量执行一次过滤，大库下有线性成本。
6. **单轮改写依赖外部 LLM**：历史改写/术语扩展/跨语言改写失败时静默退回原 query，效果会退化但不会报错。
