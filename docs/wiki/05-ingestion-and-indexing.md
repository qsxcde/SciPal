# 05 文档摄取与索引

覆盖"上传 PDF → 可检索"的完整链路。相关代码：

- 落盘与建行：`backend/src/backend/application/documents.py`
- 调度：`backend/src/backend/worker/runner.py`
- 状态机与产物：`backend/src/backend/application/ingestion.py`
- 解析与切块：`backend/src/backend/rag/ingestion/`
- 索引提交：`backend/src/backend/application/indexing.py`、`backend/src/backend/rag/indexing/vector_store.py`

## 1. 阶段总览

```
① 上传（请求线程，同步）
   documents(uploaded) + jobs(queued) + PDF 落盘                        → 202

② 调度（runner 线程）
   tick → 取 1 条 queued job → CAS 置 running(attempt+1) → 加会话锁

③ 解析（parsing）
   process_pdf_document：解析器链 → RawParserResult → DocumentIR → chunks

④ 产物落盘 + 元数据回写（parsed）
   document.ir.json / document.md / document.normalized.md / quality_report.json

⑤ 切块入库（chunked）
   delete_chunks_for_document + insert_chunks（同事务重算 chunk_count）

⑥ 建索引（indexing）
   取目标 chunks → 过滤参考文献 → 追加到上一 ready 快照 → 写候选文件

⑦ 提交（ready）
   快照 building → ready；旧 ready → stale；upsert retrieval_indexes；文档 ready
```

任一阶段抛异常 → `_mark_failed`：快照 `failed`、删 chunks、清产物字段与目录、`discard_store`、文档 `failed`、`job failed`。

## 2. 上传落地

`documents.intake_document_upload`：

1. `_validate_upload`：`file_size` 为 `None` → 400；超过 `upload_max_bytes`（默认 50 MiB）→ 413；前 4 字节不是 `%PDF` → 400。路由传入的是 `file.size`，为空时退化为 `len(pdf_bytes)`。
2. `paths.session_document_file_path` → `<data>/raw/<session_id>/<document_id>.pdf`。
3. `documents.create_document`：硬编码 `status="uploaded"`、`chunk_count=0`、`error_message=NULL`。
4. `jobs.create_job`：`type="document_ingestion"`、`status="queued"`、`stage="uploaded"`、`payload_json={document_id, filename, file_path}`、`attempt=0`。
5. `sessions.touch_session`。
6. 若会话标题仍是 `settings.msg_default_session_title`，改为文件名。

写盘与建行不在同一事务中，但有显式补偿：`create_document` 或 `create_job` 抛错时，`delete_document` + `unlink` 已写文件后再抛出（`documents.py:68-73`）。`touch_session` 与"标题自动改名"在 `try` 之外，且用 `suppress` 包裹，失败只影响排序/标题，不影响上传结果。

## 3. 任务调度

`InProcessJobRunner`（`worker/runner.py`）：

| 行为 | 实现 |
|---|---|
| 线程 | daemon 线程 `scipal-job-runner`，`runner_idle_poll_interval=0.05s` 空转 |
| 取任务 | `list_runnable_jobs(limit=1)`：`status='queued' ORDER BY created_at ASC` |
| 领取 | `mark_job_running` CAS：`WHERE id=? AND status='queued'`，`attempt+1`，清 `error_message`，置 `started_at` |
| 串行 | 每 `session_id` 一把 `threading.Lock`，同会话任务不并发 |
| 分发 | `worker/runner.py` 按 `jobs.type` 查 handler 注册表；未注册的类型直接失败，新增任务类型不需要改 runner |
| 执行 | `worker/handlers.ingest_document`：要求 `stage=uploaded`；读 `payload_json` → 读 PDF 字节 → `application.ingestion.run_document_ingestion_job` |
| 收尾 | 成功 `mark_job_finished("succeeded")`；异常 `mark_job_finished("failed", str(exc))` |
| 恢复 | 启动时 `recover_interrupted_jobs`：`running` / `interrupted` → `queued`，清时间戳与错误 |

单线程 + 单条领取意味着多文档上传是**排队**处理，吞吐取决于单个 PDF 的解析耗时。

## 4. 解析器链

`rag/ingestion/pipeline.py:22-30` 构建候选链，按顺序尝试，第一个成功即返回：

```
[mineru_api（仅当配置 MINERU_API_KEY）] → mineru（本地 CLI） → text_pdf（pypdf 兜底）
```

全部失败 → `PaperParseError("Failed to parse PDF: <第一个后端的错误>")`。
传 `parser_backend=` 参数时只使用指定后端（测试/评测用）。

`ParserBackend` 协议（`parser_backend.py`）：

```python
class ParserBackend(Protocol):
    name: str
    version: str
    def parse(self, pdf_bytes: bytes, filename: str | None = None) -> RawParserResult: ...

class RawParserResult(BaseModel):
    markdown: str
    page_count: int
    pages: list[dict] = []
    metadata: dict = {}
    source_parser: str | None = None
    warnings: list[str] = []
```

| 后端 | name / version | 布局信息 | 关键行为与限制 |
|---|---|---|---|
| `MinerUApiBackend` | `mineru_api` / `1.0` | 有（按页分组 blocks） | MinerU 云 API v4：申请签名 URL → PUT 上传 → 轮询 `extract-results/batch` → 下载结果 ZIP；`model_version="vlm"`，强制 formula/table；单文件 ≤ 200 MiB；`mineru_api_timeout=300`、轮询 `2.0s`、总轮询上限 `600s`；结果优先级 `*content_list_v2.json` → `*content_list.json` → `content.json`；`image/chart` 只保留 caption，无 caption 则丢块 |
| `MinerUBackend` | `mineru` / `unknown` | 无（`pages=[]`，只有 `full.md`） | 子进程 `mineru -p ... -o ... -b pipeline`，超时硬编码 600s；模型缓存不完整直接抛错；注入 `MINERU_MODEL_HOME/SOURCE/DEVICE_MODE/MODELSCOPE_CACHE/TABLE/FORMULA/DISABLE_OCR`；`mps` 失败且错误含 mps/metal 时自动重试一次 `cpu` |
| `TextPDFBackend` | `pypdf-text` / `unknown` | 有（整页单栏） | `pypdf` 抽文本，空页跳过；每页按词数切块 `clamp(max_chunk_tokens//3, 80~180)`；bbox 为整页、`type="paragraph"`、`confidence=0.5`；加密 PDF 抛 `RuntimeError` |

## 5. 归一化（`normalizer.py`）

输入 `RawParserResult`，输出 `DocumentIR`：

1. 扫描页边缘重复文本 → 判为页眉页脚（同一文本出现在 ≥2 页的页边区域）。
2. 逐页阅读顺序排序：双栏检测（≥4 块、左右各 ≥2 块、左列最右 < 右列最左，列缝 > 页宽 5%）→ 栏内按 `(y0, x0)`。
3. 丢弃空文本块（`formula` 例外）；空文本且 bbox 全 0 的块告警跳过。
4. 类型判定：解析器已给合法类型则沿用，否则走 `detect_block_type` 启发式。
5. 丢弃纯视觉块（`image/figure/picture` 且非 caption）。
6. 标题 → 更新 `section_path` 并 `clean_heading` 去编号；维护 `in_references` 状态（`references` 开启，appendix/supplementary/acknowledgments 关闭）；`reference` 块强制 `section_path=["References"]`。
7. 生成 `BlockIR`：`id = f"p{page_number}-ro{reading_order}"`，`reading_order` 全文档单调递增。
8. 页内 `attach_caption_links`：caption → 最近的 table/figure，`relation="caption_for"`。
9. 汇总 `outline`（heading 文本序列）与 `QualityReport`。

### 块类型启发式（`block_classifier.py`）

| 规则 | 判定 |
|---|---|
| 纯数字 + 位于页边距 | `header_footer` |
| 跨页重复 + 位于页边距 | `header_footer` |
| 命中 `HEADING_PATTERN`（abstract/introduction/conclusion/references/数字编号）且 ≤12 词 | `heading` |
| 参考文献区内 `^\[\d+\]` | `reference` |
| 含 `fig./figure/图` | `figure_caption` |
| 含 `table/表` | `table_caption` |
| 以 `\|` 开头且 `\|` ≥ 2 个 | `table` |
| ≤12 词且含 ≥2 个数学符号 | `formula` |
| 其它 | `paragraph` |

默认置信度：`header_footer 0.99`；`heading/reference/figure_caption/table_caption/table 0.93`；`paragraph 0.9`；`formula 0.7`（空文本 0.3）；`unknown 0.4`。
页边距阈值：`y1 ≤ 0.1H` 或 `y0 ≥ 0.9H`。

## 6. 质量报告（`quality_reporter.py`）

| 指标 | 计算 |
|---|---|
| `text_block_count` | `type == paragraph` 数 |
| `heading_count` | `type in {heading, title}` 数 |
| `low_confidence_block_count` | `confidence < 0.5` 数 |
| `filtered_header_footer_count` | `header_footer` 块数（不参与切块） |
| 其它计数 | table / figure_caption / table_caption / formula |

`overall_status` 判定：

- 无 blocks 且无 heading → `failed`
- 无 blocks 或 `heading_count == 0` → `poor`
- 否则 `good`；若同时存在 warning → `usable_with_warnings`

warning 例：`NO_HEADINGS_DETECTED`、`LOW_TEXT_DENSITY`。

结果随文档落库为 `parse_quality_status`，并写入 `quality_report.json`。

## 7. 切块（`chunking.py`）

流程：

1. 跳过 `title / heading / header_footer`。
2. 代码块（以 ` ``` ` 开头）单独成块；`reference` 单独成块。
3. 可合并类型 `{paragraph, figure_caption, table_caption, reference}` 进缓冲区，`section_path` 变化时 flush。
4. 其它类型 flush 后单独成块。
5. 超限时按分隔符递归切分，再按 `chunk_size` 聚合，尾部按 **字符** 重叠 `chunk_overlap`。

单位与参数：

- 实际传入 `chunk_size = settings.max_chunk_tokens(800)`、`chunk_overlap = settings.chunk_overlap_tokens(100)`。
- `DEFAULT_CHUNK_SIZE=2000` / `DEFAULT_CHUNK_OVERLAP=120` 仅在未传参时生效。
- token 估算：`cjk_chars / 1.5 + other_chars / 4`（最小 1），不是真实 tokenizer 计数。
- 分隔符 `["\n\n", "\n", ". ", "。", "！", "？", " ", ""]`。

`Chunk` 元数据填充规则：

| 字段 | 规则 |
|---|---|
| `text` | `"{heading_prefix}\n\n{body}"`，`section_path` 逐级生成 `##`…`######` |
| `section` | `" > ".join(section_path)` |
| `chunk_index` | 同文档内全局自增 |
| `type` | 合块时降级为 `paragraph`，代码块为 `code`，其余保留主类型 |
| `page_start/page_end` | 合块取 min/max；markdown 兜底为 `None` |
| `bbox` | 合块取并集；兜底 `None` |
| `block_ids` / `block_types` | 合块 id 列表 / 去重类型；兜底 `[]` / `["markdown"]` |
| `linked_block_ids` | `links` 目标 id 去重；无则 `None` |
| `confidence` | 合块取 **min**；兜底 `0.5` |

两级降级：IR 切不出块 → 用原始 markdown 重切（`type="markdown"` 兜底块）；仍为空 → 用首个标题造单块（`section="Abstract"`, `confidence=0.3`, page 1-1）；再失败 → `PaperParseError("NO_RETRIEVABLE_CHUNKS: ...")`。

## 8. 产物文件

`save_ingestion_artifacts` 写入 `<data>/raw/<session_id>/parsed/<document_id>/`：

| 文件 | 内容 |
|---|---|
| `document.ir.json` | `DocumentIR.model_dump(mode="json")`，`sort_keys=True, indent=2` |
| `document.md` | 原始解析 markdown（为空则退化为 normalized） |
| `document.normalized.md` | `export_markdown(DocumentIR)` 结果，跳过 `header_footer` |
| `quality_report.json` | `QualityReport` JSON |

前三个中的 IR / markdown / quality 报告路径回写到 `documents` 表；`document.normalized.md` 只落盘不入库。

## 9. 索引构建与提交

### 9.1 候选快照

`indexing.build_candidate_snapshot`：

1. `uuid4()` 生成 token，`create_building_snapshot` 写 `index_snapshots(status=building, document_ids_json=[...])`。
2. 取目标 chunks（当前会话全部可索引块），`filter_indexable_chunks` 剔除参考文献块。
3. 增量构建：若存在 previous ready 快照，`FAISSVectorStore.load(prev)` 后只追加"不在 `document_ids` 中"的新文档块；否则新建 store 全量索引。
4. `store.save(index_path, chunks_path)` 写两份文件；失败 → `SnapshotCommitError(candidate_snapshot=..., preserve_candidate_snapshot_files=False)`。

关键语义：**快照是整会话累积索引**，不是单文档索引。新文档 = 旧 ready 快照 + 新块。

### 9.2 提交

`indexing.commit_ready_snapshot`：

```
校验：快照存在、session 匹配、document_id ∈ snapshot.document_ids
  → mark_snapshot_ready
        同事务：同会话其它 ready → stale；目标 building → ready
  → upsert retrieval_indexes(status=ready, 指向新路径)
  → documents.update_document_status(ready, chunk_count)
  → registry.discard_store(session_id)
```

### 9.3 回滚

任何一步失败：

1. `rollback_snapshot_promotion`：旧 `stale → ready`，新快照 `ready → failed`（写 `error_message`）。
2. 若 `retrieval_indexes` 已发布，恢复旧行；无旧行则写 `status='failed'`。
3. `discard_store` 清缓存。

`SnapshotCommitError.preserve_candidate_snapshot_files=True` 时保留候选文件以便排查，否则删除。

### 9.4 读取侧

`registry.get_store` 优先读 `retrieval_indexes`（legacy），其次 active ready 快照，再次从 `chunks` 内存重建，最后空 store。详见 [03 数据模型与存储](03-data-model.md) 第 6 节。

## 10. 失败清理

`ingestion._mark_failed` 统一处理：

1. 若存在候选快照 → `mark_snapshot_failed`，按 `preserve_candidate_snapshot_files` 决定是否删文件。
2. `delete_chunks_for_document`（`chunk_count` 归零）。
3. 清空 `documents` 的 `parsed_ir_path` / `parsed_markdown_path` / `quality_report_path` / `parser_name` / `parser_version` / `parse_quality_status`。
4. 校验路径安全后删除 `parsed/<document_id>` 目录（`_is_safe_parsed_artifact_dir` 双重校验）。
5. `registry.discard_store`。
6. `update_document_status(failed, error=str(exc))`。

原始 PDF 保留（便于人工排查）。

## 11. 关键参数

| 参数 | 默认 | 位置 |
|---|---|---|
| `upload_max_bytes` | 52428800（50 MiB） | `config.py` |
| `max_chunk_tokens` | 800 | `config.py` → `ingestion/pipeline.py` |
| `chunk_overlap_tokens` | 100 | 同上 |
| `mineru_torch_device` | `cpu` | `config.py` |
| `mineru_disable_ocr` | `True` | 同上 |
| `mineru_table_enable` / `mineru_formula_enable` | `True` / `True` | 同上 |
| `mineru_api_key` | `None`（为空则不启用云解析） | 同上 |
| `mineru_api_timeout` / `mineru_api_poll_interval` / `mineru_api_max_poll_time` | 300 / 2.0 / 600 | 同上 |
| `runner_idle_poll_interval` | 0.05 | 同上 |
| MinerU 本地子进程超时 | 600s（硬编码） | `ingestion/mineru_backend.py` |
| MinerU API 单文件上限 | 200 MiB（硬编码） | `ingestion/mineru_api_backend.py` |
| 低置信阈值 | 0.5（硬编码） | `ingestion/quality_reporter.py` |

## 12. 扩展点

**新增解析后端**：

1. 在 `rag/ingestion/` 实现 `ParserBackend`（`name`、`version`、`parse`）。
2. 在 `pipeline._build_parser_chain` 中按优先级插入。
3. 若后端不返回 `pages`，只靠 `markdown` 也能工作（会走 markdown 兜底切块）。

**调整切块策略**：改 `chunking.py` 的 `MERGEABLE_TYPES` / `SEPARATORS` / token 估算；若改单位语义，需同步 `settings.max_chunk_tokens` 的注释与评测预期。

**改变索引可见性**：不要绕过 `commit_ready_snapshot` 直接写 `index_snapshots.status`，否则 `retrieval_indexes` 与文档状态会与实际不一致（这正是回滚逻辑存在的原因）。
