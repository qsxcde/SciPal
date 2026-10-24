# 09 离线评测

代码：`backend/src/scipal_eval/`
入口：`scipal-eval` 控制台脚本 / `python -m scipal_eval.cli`（`prog="ragas-evals"`）

评测在**当前进程内**直接调用应用服务层（`evaluation.evaluate_session_retrieval` / `evaluation.evaluate_session_chat`），不经过 HTTP，因此需要能读到同一份 SQLite 与会话索引文件。

## 1. 前置条件

- 已有一个建好索引的会话（`index_snapshots` 中存在 ready 快照），且 `--session-id` 指向它。
- 数据集样本的 `document_id` 必须属于该会话。
- 纯检索评测不需要 `DEEPSEEK_API_KEY`；开启生成/RAGAS/Judge 才需要。

## 2. 子命令

| 子命令 | 主要参数 |
|---|---|
| `run` | `--dataset`（必填）、`--config-set`（必填）、`--output-dir`（必填）、`--run-name`（必填）、`--session-id`、`--allow-draft`、`--with-generation`、`--with-ragas`、`--suite{retrieval,generation,e2e,all}`（默认 retrieval）、`--profile{regression,judge,full}`（默认 regression）、`--with-judge`、`--judge-model`（默认 `deepseek-v4-pro`）、`--fail-on-regression`、`--thresholds`、`--threshold-config` |
| `compare` | `--baseline`、`--current`（均为 `summary.json` 路径） |
| `baseline-save` | `--run-dir`、`--output` |
| `generate-draft` | `--session-id`、`--output`、`--max-samples`（默认 30）、`--question-types`、`--generator-model`、`--no-llm` |

约束：

- `--with-ragas` 必须同时 `--with-generation`。
- 多 config 集合下使用 `--fail-on-regression` 必须显式指定 `--threshold-config`。
- `profile` 会隐式开启开关：`full` → RAGAS + Judge；`judge` → Judge。

`scoring_mode` 取值：`retrieval_only` / `generation_only` / `generation_with_ragas`；跳过生成时会在 `run_config.json` 的 `warnings` 记一条说明。

## 3. 运行流程

```
load_dataset(allow_draft)                  # JSONL 校验
get_config_set(name)                       # 取检索配置数组
dataset_fingerprint()                      # 规范化 JSON 的 sha256
for sample in samples:
    for config in configs:
        evaluator = evaluate_session_retrieval | evaluate_session_chat
        # 仅 status == "complete" 才计算指标，异常记为 failed
可选：RAGAS 打分 → Judge 打分
写产物（jsonl / summary / report / failures）
可选：阈值门禁（违规 → SystemExit）
```

## 4. 数据集格式

JSONL，一行一个 `EvalSample`（`scipal_eval/models.py`，`extra="forbid"`）。

必填字段：`sample_id`、`document_id`、`question`、`reference_answer`、`question_type`、`difficulty`、`review_status`（`draft` / `approved`）。

可选字段：

| 字段 | 说明 |
|---|---|
| `session_id` | 覆盖 `--session-id` |
| `expected_contexts` | `[{chunk_index, section, text, relevance_grade(0-3)}]`，`relevance_grade` 用于 nDCG |
| `expected_sections` / `expected_chunk_indices` | 命中判定目标 |
| `expected_evidence_text` / `expected_citations` | 生成侧判定 |
| `answer_requirements` / `negative_requirements` | Judge 参考 |
| `requires_abstention` | 应拒答样本 |
| `generator` / `notes` | 元信息 |

校验规则：

- `review_status="draft"` 必须加 `--allow-draft`。
- `requires_abstention=True` 时不得同时提供 `expected_sections` / `expected_chunk_indices`。
- 非拒答样本必须提供 `expected_sections` 或 `expected_chunk_indices` 之一。
- `sample_id` 全局唯一；空文件报错。

`dataset_fingerprint` 按 `sample_id` 排序后对规范化 JSON 求 sha256，与行序无关。

## 5. 配置集

`scipal_eval/configs.py`：

| 配置集 | 包含配置 |
|---|---|
| `retrieval-v1` | `dense_baseline`、`hybrid_default`、`hybrid_no_expand`、`hybrid_top8_seed`、`hybrid_adjacent_window_2` |
| `hybrid-v1` | `dense_baseline`、`bm25_only`、`hybrid` |
| `reranker-v1` | `hybrid_no_reranker`、`hybrid_reranker` |
| `reranker-hr` | 同 `reranker-v1`，但 `bm25/dense/seed_top_k=12`、`rerank_top_k=10` |

`RetrievalConfig` 字段：`name, top_k, max_expanded_chunks, same_section_window, adjacent_window, include_linked_blocks, strategy(dense|bm25|hybrid), bm25_top_k, dense_top_k, seed_top_k, rrf_k, enable_reranker, rerank_top_k`。

## 6. 指标

### 6.1 确定性检索指标（`metrics.calculate_retrieval_metrics`）

| 指标 | 含义 |
|---|---|
| `chunk_hit_rate` | 是否命中任一期望 chunk（0/1 均值） |
| `chunk_recall` | 期望 chunk 的召回比例 |
| `section_hit_rate` / `section_recall` | 章节级命中/召回 |
| `mrr` | 首个相关 chunk 的倒数排名 |
| `recall_at_k` | top-k 召回 |
| `ndcg_at_k` | 需 `expected_contexts.relevance_grade`，否则为 `None` |
| `retrieved_context_count` | 返回块数 |
| `empty_retrieval` | 是否空检索 |
| `token_budget_proxy` | 拼接上下文的总字符数（代理指标） |

`requires_abstention=True` 的样本，`mrr / recall_at_k / ndcg_at_k` 强制为 `None`，不参与均值。

### 6.2 RAGAS（`score_ragas_metrics`）

- 仅对 `status == "complete"` 的结果计算。
- `metrics=[Faithfulness, ContextRecall, ContextPrecision, AnswerRelevancy]`，`raise_exceptions=False`。
- 别名：`groundedness = faithfulness`、`answer_relevance = answer_relevancy`。
- embedding 使用 `settings.embedding_model`（HuggingFaceEmbeddings）；需要 `DEEPSEEK_API_KEY`。

### 6.3 LLM Judge（`judge.py`）

`ChatOpenAI(temperature=0)`，模型优先级：`SCIPAL_EVAL_JUDGE_MODEL` > `--judge-model`。

输出 JSON：`completeness, citation_accuracy, hallucination_rate, task_success_rate, end_to_end_answer_quality, abstention_accuracy, rationale`，分数 clamp 到 `[0,1]`。

解析或调用失败不中断评测，写入 `result.judge_warning`，并汇总到 `failures.md`。

## 7. 产物结构

`<output-dir>/<run_id>/`，`run_id = <安全化 run_name>-<UTC %Y%m%d%H%M%S>`：

```
├── run_config.json            # RunMetadata（dataset_fingerprint、profile、suite、thresholds、warnings、reproducibility_manifest）
├── dataset_fingerprint.txt
├── samples.jsonl              # 输入样本
├── results.jsonl              # 每 sample×config 的结果与指标
├── summary.json               # suite_metrics / overall_by_config / grouped_by_config / failure_summary
├── report.md                  # 各 config 指标
├── comparison.md              # 以 top5_default > dense_baseline > 首个 config 为基线的 delta
└── failures.md                # status=failed 或 judge_warning 的样本
```

`compare` 的可比性门槛：`dataset_fingerprint` 与 `reproducibility_manifest` 必须完全一致，否则输出 `Comparable: false` 及原因。`reproducibility_manifest` 记录会话 active ready 快照的 `id / updated_at / document_ids` 与 `embedding_model`。

## 8. 阈值

默认文件 `backend/src/scipal_eval/configs/eval_thresholds.yaml`：

| suite | metric | 规则 |
|---|---|---|
| retrieval | `recall_at_k` | `min: 0.8` |
| retrieval | `ndcg_at_k` | `min: 0.75` |
| generation | `faithfulness` | `min: 0.85` |
| generation | `hallucination_rate` | `max: 0.05` |
| e2e | `task_success_rate` | `min: 0.8` |
| e2e | `abstention_accuracy` | `min: 0.9` |

解释规则（`thresholds.py`）：

- 逐 `suite.metric` 读 `summary.suite_metrics`；**指标为 `None` 时静默跳过，不判违规**。
- 违规汇总为 `ThresholdViolation{metric_path, actual, rule}`，抛 `SystemExit("Evaluation thresholds failed: ...")`。
- `--threshold-config` 会把 `suite_metrics` 限定到该 config；默认取单一配置名。

推论：只跑检索时，`--fail-on-regression` 实际只能约束 `recall_at_k` / `ndcg_at_k`。

## 9. 草稿生成

`generate-draft` 从已入库 chunks（过滤 `len(text.strip()) >= 40`）批量生成 `review_status="draft"` 样本。

默认 8 种题型：`summary, method, result, comparison, limitation, definition, evidence, abstention`。

`--no-llm` 时使用模板拼装（无需模型 key），否则调 `deepseek-v4-pro` 生成。

## 10. 常用命令

```bash
# 纯检索（默认 suite=retrieval、profile=regression）
uv run --project backend python -m scipal_eval.cli run \
  --dataset data/evaluation/reviewed/retrieval-v1.jsonl \
  --session-id session-example \
  --config-set retrieval-v1 \
  --output-dir eval_outputs/ragas \
  --run-name retrieval-exp-001

# 生成 + RAGAS
uv run --project backend python -m scipal_eval.cli run \
  --dataset data/evaluation/reviewed/retrieval-v1.jsonl \
  --session-id session-example \
  --config-set retrieval-v1 \
  --output-dir eval_outputs/ragas \
  --run-name retrieval-exp-001-live \
  --with-generation --with-ragas

# 对比两次运行
uv run --project backend python -m scipal_eval.cli compare \
  --baseline eval_outputs/ragas/run-a/summary.json \
  --current  eval_outputs/ragas/run-b/summary.json
```

## 11. 限制

1. 评测依赖真实会话索引，不能对任意 PDF 临时跑。
2. `token_budget_proxy` 是字符数代理，不是真实 token。
3. RAGAS 需要联网调用 DeepSeek 与 HuggingFace embedding，耗时与费用高。
4. 阈值缺失即通过，CI 里容易"绿灯但没测"。
5. 评测产物 `eval_outputs/` 与 `data/` 均被 `.gitignore` 忽略，不会入库。
