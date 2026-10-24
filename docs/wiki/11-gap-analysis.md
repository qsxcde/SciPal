# SciPal 能力缺口分析

> 视角：以"智能论文助手"的产品标准评估当前实现，而非以 RAG demo 的标准。
> 结论均可在代码中复核，证据以 `路径:行号` 标注。

## 0. 文档信息

| 项 | 内容 |
|---|---|
| 评估对象 | SciPal 当前工作副本（`main`，SQLite `user_version = 5`） |
| 核对日期 | 2026-10-25 |
| 评估范围 | `backend/src/backend`、`backend/src/scipal_eval`、`frontend/src`、`.github/workflows` |
| 评估方法 | 静态阅读 + 调用链核对；未执行端到端实测与压测 |
| 结构基线 | 分层重构后（`api` / `application` / `worker` / `rag` / `storage`），提交 `e7325d2` |
| 关联文档 | [Wiki 目录](README.md)（工程事实基线）、[README](../../README.md)（使用入口） |

**路径约定**：表格中的简写路径默认相对 `backend/src/backend/`（如 `application/chat.py`）；以 `frontend/`、`docs/`、`.github/` 开头的路径相对仓库根目录。

## 1. 结论摘要

**一句话**：后端的"状态与索引工程"已经达标，但产品化与可信度严重滞后——当前交付物是**单篇 PDF + 单轮问答的 RAG 应用**，还不是"智能论文助手"。

核心判断有三条：

1. **引用不可追溯**。后端已产出 `SourceRef`（含页码、chunk 序号、置信度），前端完全不渲染，也没有 PDF 阅读器承接定位。这是论文助手的第一性要求，缺失即失去可信度。
2. **多轮对话在生成侧断裂**。检索 query 会做历史改写，但送给 LLM 的 prompt 只有"当前问题 + 检索片段"。追问语义对得上，回答仍会失忆。
3. **主链路无测试保护**。22 个用例全部落在仓储与状态机；检索、索引构建、SSE 协议、解析降级没有任何自动化验证，CI 也不安装真实依赖。

### 能力评级

| 维度 | 现状 | 评级 |
|---|---|---|
| 摄取状态机与索引原子提交 | 设计完整，失败可回滚 | A |
| 混合检索链路 | BM25 + Dense + RRF + Rerank 齐备 | B+ |
| 多轮对话 | 仅检索侧改写，生成侧无历史 | D |
| 引用与可追溯性 | 后端有数据，前端无呈现，无定位 | F |
| 文档管理 | 只有"上传"，无删除/替换/重试 | D |
| 前端产品完成度 | 单视图问答壳，多处 UI 占位 | D |
| 扩展性 | 单进程 + 精确索引 + 全量内存 | D |
| 可观测性与运维 | 仅基础日志，无 metrics/trace | D |
| 测试与发布门禁 | 主链路 0 覆盖 | F |

## 2. 现状基线（已具备的能力）

避免把"没做"误判为"缺失"，先明确已有能力：

| 能力 | 实现位置 | 说明 |
|---|---|---|
| 异步摄取 + 崩溃恢复 | `backend/src/backend/worker/runner.py`、`main.py:29-44` | 启动时重排在途 job，`mark_job_running` 用 CAS 防重复执行 |
| 索引快照原子发布 | `backend/src/backend/application/indexing.py` | 先建 candidate、再提升 ready，失败不影响已发布索引 |
| 混合检索 | `backend/src/backend/rag/retrieval/hybrid_retriever.py` | BM25 + Dense 召回、RRF 融合、rerank、上下文扩展 |
| 跨语言检索改写 | `backend/src/backend/rag/retrieval/query_rewriter.py` | 中英查询包生成，术语扩展 |
| 多 provider 降级 | `backend/src/backend/rag/generation/model_client.py` | DeepSeek → GLM/Qwen → Ollama |
| SSE 流式协议 | `backend/src/backend/api/routes/chat.py`、`application/chat.py` | `status` / `token` / `warning` / `sources` / `done` |
| 离线评测 CLI | `backend/src/scipal_eval/` | 检索指标、RAGAS、LLM Judge、阈值门禁 |
| 用户隔离 | `backend/src/backend/domain/access.py` | 会话级归属校验，越权按 404 处理 |

## 3. P0 缺口（阻塞"可信"，建议优先处理）

### G-01 · 引用无法定位到原文

- **现象**：回答里只有 `[Section: 章节名]` 文本标记；`sources` 事件返回了页码与片段，但界面上没有任何来源区域。
- **证据**：
  - `frontend/src/components/MessageBubble.vue:40-52` 只渲染正文与复制按钮，`message.sources` 未被使用
  - `frontend/src/components/MessageList.vue:29` 中 `sources` 唯一用途是滚动监听签名
  - 全仓库无 PDF 渲染组件、无引用点击跳转逻辑
- **影响**：用户无法验证回答是否真实来自论文，也无法回到原文精读。对学术场景而言，这等价于"不可引用"，直接决定产品是否可信。
- **建议**：
  1. 消息气泡下方增加来源卡片（章节 + 页 + 摘要），点击打开 PDF 并跳转到对应页；
  2. 后端 `SourceRef` 补充 `document_id` 与 `file` 访问路径，前端按 `page_start` 定位；
  3. 中期引入 PDF.js 高亮层，用 `bbox` 做区域标注。

### G-02 · 生成侧丢失多轮上下文

- **现象**：只有检索 query 经过 `history_aware_rewrite`，生成 prompt 只接收"片段 + 当前问题"。
- **证据**：
  - `backend/src/backend/rag/generation/answer_generator.py:10-17`：`build_prompt(chunks, question)` 无 history 参数
  - `backend/src/backend/rag/answer.py:159-165`：`history` 只传给 `retrieve_context`
- **影响**：追问"它的参数量是多少""和上一节的方法比呢"时，检索能命中正确片段，但模型不知道"它"指什么，回答会脱节或复述。
- **建议**：
  1. prompt 增加最近 N 轮 `(user, assistant)` 摘要，并明确"当前问题 + 历史";
  2. 历史按 token 预算截断，优先保留最近 2 轮原文 + 更早轮次的摘要;
  3. 对含指代的问题，在生成前校验历史是否注入成功（可写单测）。

### G-03 · 主链路零测试，CI 信号失真

- **现象**：现有 22 个用例只覆盖 SQLite 仓储、上传入口、鉴权与快照 GC；CI 只安装 `pytest/fastapi/pydantic`，不装 `torch/faiss`。
- **证据**：
  - `.github/workflows/ci.yml:29-40`：依赖列表不含 RAG 依赖，只有 `compileall` + `pytest -m "unit or integration"`
  - `backend/src/backend/rag/**`、`api/routes/chat.py` 无对应测试文件
- **影响**：检索参数调整、SSE 协议变更、嵌入模型切换都可能在"CI 全绿"的情况下破坏线上行为；`compileall` 只能证明语法正确。
- **建议**：
  1. 用假 embedder + 假 LLM（monkeypatch）覆盖 `retrieve_context`、`stream_answer`、`consume_stream` 的协议分支；
  2. CI 增加一个"轻依赖"job：装 `faiss-cpu`（不装 torch），跑检索与 SSE 用例；
  3. 把评测 CLI 的 `retrieval-v1` 固定数据集纳入 nightly，产出 `recall_at_k` 趋势。

## 4. P1 缺口（明显影响体验或可维护性）

| 编号 | 缺口 | 证据 | 影响 | 建议 |
|---|---|---|---|---|
| G-04 | SSE 阶段事件不真实 | `application/chat.py:140-141` 在检索开始前连续发出 `retrieving` / `generating` | 用户看到的"检索中"是假的，进度不可信 | 把 `yield` 移到实际阶段边界；检索/生成拆成显式子步骤 |
| G-05 | 前端丢弃 `status` 事件 | `frontend/src/composables/useChatStream.ts` 只处理 `token` / `sources` / `error` | 后端已实现的阶段信息在 UI 层浪费 | 增加阶段指示器（检索 → 重排 → 生成） |
| G-06 | 引用校验以章节名为唯一键 | `rag/answer.py:262-265` | 多篇论文或同名章节（多个 `Method`）会误判引用有效 | 改用 `document_id + chunk_index` 作为引用标识 |
| G-07 | 引用不合规只给 warning | `rag/answer.py:180-185` | 幻觉回答仍会落库并展示，只多一句提示 | 引入重试或"降级为拒答"策略 |
| G-08 | 无消息级操作 | `frontend/src/components/MessageActions.vue` 仅"复制回答" | 不能重生成、编辑追问、停止生成、点赞点踩 | 补 `regenerate` / `stop` / `feedback` 三个动作与对应 API |
| G-09 | 无 token 预算与上下文压缩 | `rag/generation/prompt_template.py:19-26` 直接拼接全部片段 | 长文档 + 8 个扩展块可能超上下文，且无去重 | 按 token 预算裁剪，重复片段合并，超限时降级 |
| G-10 | BM25 缓存全局单槽 | `rag/retrieval/hybrid_retriever.py:22,34-44` | 多会话交替时每次请求全量重建，延迟抖动 | 改为按 `session_id` 的 LRU（与向量库同策略） |
| G-11 | 每次检索全量拉取 chunk | `rag/retrieval/hybrid_retriever.py:166` | 会话规模上升后 O(n) 常驻内存与遍历 | 与快照绑定做进程级缓存，避免每次 `list_chunks` |
| G-12 | 无 paper 级检索过滤 | `application/policies.py:11-28` 的检索参数无论文维度 | 多文档会话无法"只在这篇里找"，也无法做论文对比 | 增加 `paper_ids` 过滤条件与"对比模式"编排 |
| G-13 | 参考文献段被整体过滤 | `rag/retrieval/filters.py:19-21` | "这篇引用了谁 / 相关工作"永远答不出 | 单开"参考文献"检索通道，或用工具调用按需开启 |
| G-14 | 摄取单线程串行 | `worker/runner.py:86-99` 每 tick 只取 1 条 job | 多用户排队，一篇慢文档阻塞全部上传 | 改为线程池 + 会话级串行，全局并发可配 |
| G-15 | 失败无重试入口 | 无 job retry 路由；`jobs` 只有 `attempt` 字段 | 用户只能重传或重建会话 | 增加 `POST /documents/{id}/retry` 与失败原因展示 |
| G-16 | 无文档级 CRUD | `api/routes/documents.py` 仅上传 | 不能删单篇、替换版本、重解析 | 补 `DELETE` / `PUT`，并同步重建快照 |
| G-17 | 无上传去重 | `application/documents.py` 无 hash 校验 | 同一 PDF 反复上传，索引重复膨胀 | 入库前算文件摘要，命中则复用 |
| G-18 | 会话快照无分页 | `storage/sqlite/messages.py:59-71` 全量返回 | 长会话首屏与切换成本线性增长 | 消息分页 + `before_id` 游标，前端懒加载 |
| G-19 | 无幂等键 | `routes/documents.py`、`routes/chat.py` | 重复点击导致重复上传/重复生成 | 引入 `Idempotency-Key`，短期内做前端防抖 |
| G-20 | 客户端断开不取消生成 | `application/chat.py:76` 用 `run_in_executor` 推进生成器 | 用户关闭页面后仍在消耗 token | 监听 `request.is_disconnected()`，取消生成器 |
| G-21 | 无 SSE 心跳 | `routes/chat.py` 仅写 `data:` 帧 | 长生成易被反向代理判超时断开 | 每 15s 发送注释帧 `: ping` |
| G-22 | 删除不彻底 | `application/sessions.py:109-112` 只置归档 + 删目录 | `messages` / `chunks` / `index_snapshots` 行永久残留 | 明确软删/硬删语义，补后台清理任务 |
| G-23 | 鉴权与配额薄弱 | `api/security.py:40-46`；无 rate limit | 开发环境匿名放行；单用户可打爆 LLM 配额 | 生产强制密钥、增加登录限流与用户级配额 |
| G-24 | 可观测性缺失 | `main.py:19-23` 仅 `basicConfig`；`main.py:65-70` 健康检查不含依赖探测 | 故障只能靠翻日志，无 trace / 慢请求定位 | 结构化日志 + request id；`/health` 增加 DB/磁盘/模型/LLM 探测 |
| G-25 | 评测不进 CI | `docs/wiki/09-evaluation.md:196` 自述"阈值缺失即通过" | 检索/生成质量无回归门禁 | 固定数据集 + 阈值必填校验，纳入 nightly |
| G-26 | 前端路由是死代码 | `frontend/src/main.ts:30-41` 未 `.use(router)`；仅有 `views/LoginView.vue` | 无页面级拆分，无法深链到会话 | 挂载 router，补 `/sessions/:id` 深链 |
| G-27 | 工具按钮为占位 | `frontend/src/components/ComposerTools.vue:59-61` 自述"工具仅提供界面状态" | 用户以为可切换检索模式/模型，实际无效 | 要么接线，要么移除 |
| G-28 | 无结构化阅读产物 | 无摘要卡/术语表/对比表/笔记/导出接口 | 用户仍需手工整理，助手价值停留在"问一句答一句" | 增加"生成摘要卡/方法对比"预设任务与导出 |

## 5. P2 缺口（增强项）

| 编号 | 缺口 | 证据 | 说明 |
|---|---|---|---|
| G-29 | 精确索引无扩展性 | `rag/indexing/vector_store.py:53` 使用 `IndexFlatL2` | 无 ANN/量化/增量；会话上万 chunk 后延迟线性增长 |
| G-30 | 无多模态理解 | `rag/ingestion/chunking.py:175-185` 仅保留 caption 文本 | 图表图像不落盘，公式纯文本；无"看图问答" |
| G-31 | 扫描件不支持 | `config.py:36` 默认 `mineru_disable_ocr=True` | 图片型 PDF 直接 `failed`，报错文案已说明但无替代路径 |
| G-32 | 解析产物不可见 | `application/ingestion.py` 落盘 markdown/quality report | 用户无法核对解析质量，排障只能看服务端文件 |
| G-33 | 无文献获取入口 | `frontend/src/components/ChatComposer.vue:70-76` 仅本地单文件 | 不支持 arXiv/DOI/URL/Zotero 导入 |
| G-34 | 无个人文献库 | 无 tag/collection；会话即论文 | 无法跨会话检索与复用文献 |
| G-35 | 上传单文件、无拖拽/进度 | `ChatComposer.vue` 只取 `files?.[0]` | 批量与拖拽缺失，进度为轮询文案 |
| G-36 | 小屏无导航 | `frontend/src/index.css:225-241` 在 1100px 以下仅把侧栏压成 76px 图标条 | 760px 以下无抽屉/汉堡菜单，移动端不可用 |
| G-37 | 刷新丢草稿 | `composables/useChatStream.ts` 的 draft 仅内存 | 无 localStorage 持久化，误刷新即丢 |
| G-38 | 单进程不可水平扩展 | `worker/runner.py`、`application/store_cache.py` | 多 worker 会重复消费 job，索引 LRU 各自为政 |
| G-39 | 无部署与备份方案 | 仓库无 Dockerfile / compose | 环境复现与数据备份全靠手工 |
| G-40 | 无国际化 | `prompts/prompts.toml`、`msg_*` 配置 | 面向中文硬编码，英文用户不可用 |

## 6. 建议路线图

### 阶段一（1-2 周）：把"可信"补上

| 任务 | 验收标准 |
|---|---|
| 生成侧注入对话历史 | 连续 3 轮指代追问（"它/该方法/上一节"）回答不脱节，附单测 |
| 引用卡片 + 页码定位 | 点击任一来源，能在原文对应页打开；无来源时明确提示 |
| 引用标识改为 `document_id + chunk_index` | 同名章节不再误判，附回归用例 |
| 主链路测试 | 检索/SSE/索引提交各有 ≥1 条用例，CI 可跑 |

### 阶段二（3-4 周）：把"好用"补上

| 任务 | 验收标准 |
|---|---|
| 文档级 CRUD + 失败重试 | 单篇可删除/重解析，失败可从 UI 一键重试 |
| 真实阶段事件 + 停止生成 | UI 阶段与后端一致；停止后不再产生 token 计费 |
| 会话分页 + 幂等键 | 100 轮会话首屏 < 1s；重复点击不产生重复记录 |
| 多文档 paper 级过滤与对比 | 可指定只在某篇内检索；可生成两篇方法对比表 |

### 阶段三（1-2 月）：把"助手"补上

| 任务 | 验收标准 |
|---|---|
| 文献导入（arXiv/DOI/URL） | 输入链接即可建索引，自动填充标题/作者/年份 |
| 笔记、导出、分享 | 支持 Markdown/PDF 导出，笔记随会话持久化 |
| 图表与公式理解 | 图表可问答，公式可解释（引入 VLM 或图像 + OCR） |
| ANN 索引与任务队列 | 支持万级 chunk，摄取并发可配，支持多 worker |

## 7. 取舍建议

以下是"不建议现在做"的决定，用于防止范围失控：

1. **先不要上分布式向量库**。当前瓶颈不是 ANN 性能，而是可信度；`IndexFlatL2` 在单会话规模下够用，先把缓存与分页做对。
2. **先不要做多租户与团队协作**。用户隔离已满足单机形态，权限模型过早复杂化会拖慢主链路修复。
3. **先不要替换 MinerU**。解析质量的主要问题是"不可见"而非"不准确"，先把质量报告暴露给用户。

## 附录 A · 关键证据索引

| 结论 | 位置 |
|---|---|
| 生成 prompt 不含历史 | `backend/src/backend/rag/generation/answer_generator.py:10-17` |
| `history` 只进检索 | `backend/src/backend/rag/answer.py:159-165` |
| 阶段事件提前发送 | `backend/src/backend/application/chat.py:140-141` |
| 引用校验以 section 为键 | `backend/src/backend/rag/answer.py:262-265` |
| BM25 全局单槽缓存 | `backend/src/backend/rag/retrieval/hybrid_retriever.py:22,34-44` |
| 每次检索全量拉 chunk | `backend/src/backend/rag/retrieval/hybrid_retriever.py:166` |
| 参考文献被过滤 | `backend/src/backend/rag/retrieval/filters.py:19-21` |
| 精确索引 | `backend/src/backend/rag/indexing/vector_store.py:53` |
| 单线程 job runner | `backend/src/backend/worker/runner.py:86-99` |
| 消息全量返回 | `backend/src/backend/storage/sqlite/messages.py:59-71` |
| 删除只置归档 | `backend/src/backend/application/sessions.py:109-112` |
| CI 不装 RAG 依赖 | `.github/workflows/ci.yml:29-40` |
| 健康检查无依赖探测 | `backend/src/backend/main.py:65-70` |
| 开发环境匿名放行 | `backend/src/backend/api/security.py:40-46` |
| 前端未使用 sources | `frontend/src/components/MessageBubble.vue:40-52` |
| 前端丢弃 status | `frontend/src/composables/useChatStream.ts`（事件分支仅 token/sources/error） |
| 路由未挂载 | `frontend/src/main.ts:30-41` |
| 工具按钮占位 | `frontend/src/components/ComposerTools.vue:59-61` |
| 单文件上传 | `frontend/src/components/ChatComposer.vue:70-76` |

## 附录 B · 评估方法与局限

- 方法：按"上传 → 解析 → 索引 → 检索 → 生成 → 引用 → 会话管理"主链路逐段阅读实现，并与 `docs/wiki` 的描述做交叉验证；前端逐组件核对数据流，确认"数据已获取但未渲染"的断点。
- 局限：
  1. 未执行真实 PDF 的端到端跑通与延迟/成本测量，性能结论基于代码结构与缓存策略推断；
  2. 未做竞品功能矩阵对照，P 级排序基于"学术阅读场景的必要性"而非市场调研；
  3. 指标阈值（如首屏 < 1s）为建议值，需结合真实数据校准。
- 维护建议：每次合并影响主链路的改动后，同步更新附录 A 的行号，避免文档腐化。
