# SciPal 整改计划（Remediation Plan）

> 制定日期：2026-10-27
> 依据：[audit-2026-10-27.md](audit-2026-10-27.md)（10 维度审计，P0/P1 均经二次读码复核）
> 适用范围：`backend/src/backend`、`frontend/src`、`tests/`、CI 与文档
> 原则：**先止血 → 再立契约 → 再动结构**。结构重构必须在契约与测试之后，否则每改一次 schema，两端同时漂移，风险翻倍。

---

## 执行进度

| 阶段 | 状态 | 已完成 | 未完成 |
|---|---|---|---|
| P0 止血 | ✅ 完成 | 0.1–0.6 全部落地 | — |
| P1 测试网 | ✅ 完成 | 1.1–1.4、1.6（1.5 并入 P2） | — |
| P2 契约 | ✅ 完成 | 2.1–2.5 全部落地 | — |
| P3 结构收敛 | ✅ 完成 | 3.1–3.6 全部落地 | — |
| P4 能力拆分 | ⬜ 未开始 | — | 全部 |
| P5 前端分层 | ⬜ 未开始 | — | 全部 |
| P6 可靠性 | ⬜ 未开始 | — | 全部 |
| P7 固化 | 🚧 进行中 | 7.3 README 修正、7.4 ruff+typecheck CI、7.5 启动自检、契约/端点表校验 | 7.1 自动生成清单、7.2 wiki 重写 |

关键变化（截至 2026-10-27）：

- 测试从 68 → 102（后端）+ 5（前端 Vitest），索引快照、SSE 顺序、摄取失败、并发均有覆盖。
- 契约链路打通：`schemas/*.py → contracts/openapi.json → frontend/src/contracts/openapi.d.ts`，
  `types.ts` 只剩别名映射，SSE 联合类型也由契约生成。
- `api/` 与 `worker/handlers.py` 不再直接访问存储；边界测试从「查一个文件」改为规则矩阵。
- 已知遗留：RAG 仍有 9 个模块在模块作用域读全局 `settings`（棘轮清单锁定，P4 清零）。
- 用例层已与 torch/faiss/openai 解耦：`application/*` 可在精简依赖下导入（有子进程用例守卫）。
- 检索层不再依赖生成层：三个改写器统一走 `composition.text_completer()`。
- lint 门禁上线：根级 `ruff.toml` + CI `ruff check`，上线即抓到一个未定义名缺陷。

---
## 0. 阶段总览与依赖

| 阶段 | 主题 | 规模 | 依赖 | 产出 |
|---|---|---|---|---|
| **P0** | 止血：4 处小时级修复 | S | 无 | 消除 P0 + 3 个 P1 |
| **P1** | 测试安全网（重构前置） | M | P0 | 6 类缺失测试 |
| **P2** | 契约单一真值 | M | P0 | `contracts/` + codegen |
| **P3** | 后端结构收敛（端口与组合根） | M | P1, P2 | `core/contracts` + `composition` |
| **P4** | 后端能力拆分（rag → adapters） | L | P3 | 按职责的包结构 |
| **P5** | 前端分层（features + stores） | L | P2 | 域目录 + 状态归位 |
| **P6** | 可靠性、并发与可观测性 | M | P4, P5 | 流式生命周期重做 |
| **P7** | 守卫与文档固化 | S | 全部 | CI 规则 + 文档校验 |

P0 / P1 / P2 可并行推进（不同目录、不同人）；**P3 之后必须串行**。

`
P0 ──┬── P1 ──┐
     └── P2 ──┴── P3 ── P4 ──┐
                       P5 ────┴── P6 ── P7
`

---

## P0 · 止血

只改已有文件里的几行，不碰结构、不改接口形状，保证主分支随时可发布。

| # | 任务 | 文件 | 验收 |
|---|---|---|---|
| 0.1 | `PersistedMessage.status` 的 `Literal` 补 `“stopped”` | `api/schemas/session.py:24` | 新增 round-trip 测试：写 stopped → `GET /sessions/{id}` 返回 200 |
| 0.2 | 统一 `.env` 到 `backend/.env`，启动打印实际加载路径；同步改 README / wiki 08 / `.env.example` | `config.py:101`、`README.md:90-93`、`docs/wiki/08-configuration.md:8-9` | 启动日志出现绝对路径；根目录放 `.env` 时打印 warning |
| 0.3 | 上传改流式：先按 `Content-Length` 拒绝超限，再分块写临时文件并累计计数 | `api/routes/documents.py:43`、`application/documents.py:27-34` | 构造 60 MiB 请求返回 413，内存峰值不随体积增长 |
| 0.4 | `logout()` 清空全部前端单例 + abort 在途流 + `useLibrary.invalidate()` + `usePaperReader.reset()` | `AppShell.vue:136-139`、`useAuth.ts:57-63`、`usePaperChat.ts:15` | 登出后 sessions/messages/documents 为空；换账号不出现他人会话 |
| 0.5 | `PdfViewer` 保存 `RenderTask`，重渲染前 `await cancel()` 并忽略 `RenderingCancelledException` | `PdfViewer.vue:51-82` | 连续快速翻 10 页无白屏、无 console 异常 |
| 0.6 | DB 移出包目录到 `data_dir()`；`.gitignore` 加 `**/*.db*`；清理 3 个未跟踪文件 | `storage/paths.py`、`.gitignore` | `git status` 干净；`SCIPAL_DATA_DIR` 生效 |

---

## P1 · 测试安全网（重构的入场券）

现状：68 个测试 2 秒跑完，但 FAISS 构建、SSE 状态机、并发、前端全部为零覆盖。P4 会大改这些路径，没有测试等于蒙眼改。

| # | 要补的测试 | 覆盖的风险 |
|---|---|---|
| 1.1 | FAISS 快照：build → promote → load → rollback 全链路（8 维假向量，不加载真模型） | P4 拆 `rag/indexing` 的唯一保障 |
| 1.2 | SSE 事件顺序：`status → token* → sources → done`，含「缺 sources 报错」「中途异常发 error」 | P6 重做流式生命周期 |
| 1.3 | 上传失败回滚：解析失败 → 文档 failed、job failed、快照不 promote、无残留目录 | P0.3、P4c 改上传链路 |
| 1.4 | 并发：同会话双请求 / 删除与摄取并发，断言无「有问无答」、无悬空快照 | P6 加锁 |
| 1.5 | 契约快照测试：`/openapi.json` 与 `contracts/openapi.json` 逐字节比对 | P2 的守卫 |
| 1.6 | 前端最小测试基建：Vitest + `useChatStream` 三个用例（正常流 / 中断重试 / 未知事件） | P5 前端重构 |

**门禁**：`pytest -m "unit or integration"` 全绿且新增 ≥15 个用例，才能开 P3。

---

## P2 · 契约单一真值

现状：`frontend/src/api/types.ts` 顶部自述「手写镜像」，`status` 在 4 处退化成 `string`，SSE 事件名两端各写一份。`stopped` 那个线上 500 就是这套结构的必然结果。

| # | 任务 | 说明 |
|---|---|---|
| 2.1 | 新增 `contracts/` 目录，CI 导出 `openapi.json` 并提交 | 新增 `backend.export_openapi` 脚本（约 3 行） |
| 2.2 | 前端接入 `openapi-typescript`，`types.ts` 改为 re-export 生成类型 | 手写部分迁到 `types/view.ts`，删掉 164 行手抄 |
| 2.3 | SSE 事件 schema 化：从 `application/events.py` 导出 JSON Schema，生成 TS 联合类型 | 前端 if/else 换穷尽 switch + never 断言 |
| 2.4 | CI 两步：`git diff --exit-code contracts/` 失败即红；`npm run gen` 后工作区必须干净 | 契约漂移从此不可能合入 |
| 2.5 | README 端点表由 `openapi.json` 生成 | 顺手消灭「7 个端点 vs 实际 15 个」的漂移 |

**验收**：删掉后端 `ChatStreamWarningEvent`，前端 `npm run typecheck` 必须编译失败。

---

## P3 · 后端结构收敛

目标不是搬家，而是**把「能力」变成端口**，让 `settings` 只在一个地方被读。

| # | 任务 | 现状证据 |
|---|---|---|
| 3.1 | 新建 `core/contracts/ports.py`：`DocumentRepository`、`IndexSnapshotRepository`、`Embedder`、`TextCompleter`、`PaperParser`、`VectorStore` | `application/sessions.py` 直接 import FAISS 的抽象基类 |
| 3.2 | 新建 `app/composition/`：唯一读 `settings` 的地方，构造适配器与用例 | 20 个模块 import 全局 settings、110 处调用 |
| 3.3 | `application/policies.py` 升级为 composition 子模块 | 它本就是 settings→参数的翻译器，方向正确 |
| 3.4 | 删除 `application/index_maintenance.py` 的函数体内延迟导入补丁 | `index_maintenance.py:24-31`，该文件因 faiss 体积而存在 |
| 3.5 | `application/store_cache.py` 下沉为适配器内部实现 | 模块级 `_stores` + `RLock`，属基础设施非用例 |
| 3.6 | 边界测试升级为矩阵规则，先让它在现状下失败，得到完整待办清单 | `tests/test_package_boundaries.py:60-63` 只查了 1 个文件 |

新增规则（写入 `test_package_boundaries.py`）：

`
rag/**         不得 import backend.config
api/**         不得 import backend.storage
worker/**      不得 import backend.storage
storage/**     函数签名不得返回裸 dict
application/** 不得 import fastapi（保留现有规则）
`

**验收**：5 条规则全绿；`grep -r "from backend.config import settings" backend/src | wc -l` ≤ 3。

---

## P4 · 后端能力拆分（风险最高）

把 4350 行的 `rag/` 杂物袋拆成「适配器 + 用例策略」。

| 现状 | 目标 | 关键改动 |
|---|---|---|
| `rag/ingestion/`(17 文件) | `adapters/parsing/` + `app/ingestion/` | 解析是 I/O，归一化与切块是领域逻辑 |
| `rag/embedding/`(4) | `adapters/embedding/` | **同时修 P1-3**：回退改为构造期决定；快照写入 `embedding_model` + `dim` 指纹并校验 |
| `rag/generation/`(5) | `adapters/llm/` + `app/chat/answer.py` | **同时修 P1-6**：`emitted=True` 后禁止换 provider |
| `rag/retrieval/`(13) | `app/chat/retrieval/` | 砍掉 retrieval → generation 反向依赖，3 个 rewriter 改为注入 `TextCompleter` |
| `rag/indexing/vector_store.py` | `adapters/vector/faiss/` | `AbstractVectorStore` 提到 `core/contracts/ports.py` |
| `storage/sqlite/*` 返 dict | `core/model/` 实体 + 仓储返回实体 | 最深的一刀：`documents.py:35` 等 8 个函数 |
| `application/documents.py`(355 行) | `app/library/{upload,delete,list}.py` | 一个文件一件事 |
| `worker/handlers.py` 直连仓储 | 只调用例，文件读取下沉 | `handlers.py:7-9` |

分批（每次一个 PR，主分支保持绿）：

1. **4a** 向量与检索（由 1.1 保护）
2. **4b** 生成与 LLM（由 1.2 保护）
3. **4c** 解析与摄取（由 1.3 保护）
4. **4d** 存储实体化（最痛，最后做；先加类型别名过渡）

**硬性前置**：1.1–1.4 全绿 + P3 边界规则就位。否则不许开工。

---

## P5 · 前端分层

| # | 任务 | 现状 |
|---|---|---|
| 5.1 | 建 `features/{chat,library,reader,sessions}/`，按域搬组件与 composable | 22 个组件平铺，`PaperReader.vue` 587 行 |
| 5.2 | 建 `stores/`，5 处模块级闭包单例收进去并给出 `reset()` | `usePaperChat.ts:15`、`useLibrary.ts:17-18`、`useAuth.ts:16`、`usePaperReader.ts:25` |
| 5.3 | 消除 `AppShell.vue` 四层 props 透传，改 store 或 provide/inject | P0 越权读的结构成因 |
| 5.4 | 拆分 `PaperReader.vue`(587) / `LibraryPanel.vue`(471) | 单文件 >300 行 |
| 5.5 | `eslint-plugin-boundaries`：feature 之间不得互相 import | 与后端边界测试同源思路 |
| 5.6 | 修 P2 前端项：切会话中断在途流、引用/正文/PDF 加载加请求序号、阅读器改用 `paperSession.docId` | `AppSidebar.vue:118`、`useSourcePreview.ts:36-58`、`AppShell.vue:53` |

**验收**：删掉 `features/chat` 目录后 `features/reader` 编译不受影响；`grep -rn "^let " frontend/src/composables` 为空。

---

## P6 · 可靠性与可观测性

| # | 任务 | 修的问题 |
|---|---|---|
| 6.1 | 流式生命周期重做：`try/finally` 里 `gen.close()`、专用线程池、落库 `create_task` + `shield` | 取消不释放、CancelledError 二次抛、默认线程池被拖慢 |
| 6.2 | per-session `asyncio.Lock` 覆盖「删旧答案 → 读历史 → 写答案」 | 跨标签页 regenerate 删掉另一路答案 |
| 6.3 | regenerate 改「先写后删」 | 生成失败即永久丢失上一轮回答 |
| 6.4 | SSE 加 15s 心跳 + `X-Accel-Buffering: no`；`waiting_for_index` 立即发 | nginx 下退化、10s 零字节 |
| 6.5 | `get_current_user` 改异步或走线程池 | 同步 SQLite 阻塞整个事件循环 |
| 6.6 | 客户端幂等键 `client_message_id` + 唯一索引；仅在「0 token 前失败」重试 | 一次抖动 = 3 条重复问答 |
| 6.7 | worker 并发 >1；前端轮询预算 ≥ 后端超时 ×1.5；区分「排队 / 解析」 | 一个慢 PDF 阻塞所有用户 10 分钟 |
| 6.8 | 删除 / 归档与运行中摄取互斥 | 归档会话被 worker 复活 |
| 6.9 | token 统计、`max_tokens`、生成总超时落库 | 成本不可核算 |

---

## P7 · 守卫与文档固化

| # | 任务 |
|---|---|
| 7.1 | 路由表、配置字段、测试清单由 `openapi.json` / `RuntimeSettings` / `pytest --collect-only` 自动生成，**禁止手写计数** |
| 7.2 | 重写 wiki 07/10/11：删掉已实现的 6 条「缺口」（含 1 条 P0），11 章从「差距分析」改为「剩余 backlog」 |
| 7.3 | README 全面修正：`cd SciPal`、`.env` 路径、CPU/MPS、端点表、测试数、fallback 默认值 |
| 7.4 | CI 增加：`ruff check`（当前未安装、无配置）、`npm run typecheck`、契约 diff 门禁 |
| 7.5 | 启动自检：`jwt_secret_key` 非空；`APP_ENV=production` 禁止匿名旁路；不满足直接启动失败 |

---

## 风险与不做清单

**风险登记**

| 风险 | 缓解 |
|---|---|
| P4 大改期间功能回归 | 每批独立 PR；1.1–1.4 为硬门槛；先加类型别名过渡再实体化 |
| codegen 与手写类型并存期混乱 | P2 一次性切换，不保留双轨；`types.ts` 改为纯 re-export |
| 前端搬迁 PR 过大难 review | 5.1 只做「移动文件 + 改 import」，零逻辑变更，单独提交 |
| 重构同时改 schema 导致双重不确定 | P3/P4 期间冻结新功能需求；契约变更走 P2 流程 |

**明确不做**

- 不引入 DI 容器（`composition` 手写构造即可）
- 不引入 ORM（现有 SQLite 仓储 + CAS 是资产，只改返回类型）
- 不换大而全的状态管理方案（Pinia 或 provide/inject 均可，关键是**有 owner、有 reset**）
- 不复制 tenon 的 `app/tui` 五层子树
- 不在 P4 之前动 `domain` / `storage` 实体化（最深的一刀，必须等测试齐）

---

## 起手第一件事

按序执行 **0.1 → 0.2 → 0.4**：三处加起来不到 30 行，但「stopped 会话 500」「鉴权静默失效」「跨账号残留」三个最严重的问题同时消失。随后开 P1 补测试。
