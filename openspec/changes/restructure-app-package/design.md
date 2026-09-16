## Context

参见 `proposal.md` 的 Why 一节了解动机。本节只记录塑造实现方式的当前状态与约束。

**当前状态**

- `app/` 计 19 个 Python 文件、1543 行，分 4 个子包 + `main.py`
- 其中 3 个 `__init__.py` 为 0 字节；`app/api/` 与 `app/core/` 各只有一个有内容的成员
- 引用关系经全仓核查：`app.core.auth` 被 4 个路由文件引用，`app.schemas` 被 3 个文件引用，`job_runner` 与 `app.api.routes` 各被 `main.py` 引用一次——**全部封闭在 `app/` 包内**

**约束**

1. **零测试覆盖**：当前仓库没有可运行的测试（`pytest.ini` 定义了 marker 但无测试文件）。因此验证不能依赖回归测试，必须依靠"结构等价性检查"
2. **运行时契约不可变**：`pyproject.toml` 的入口点、README 的启动命令、`.env` 路径、数据目录布局、SQLite schema 均不得变动
3. **纯位移**：不修改任何函数签名、不改变任何调用语义——这是本变更能被安全执行的前提

## Goals / Non-Goals

**Goals**

- 消除 `app/` 包内的层级冗余与命名冲突，使每个目录名能直接指向其内容
- 使"路由层不直接访问存储"成为无例外的规则
- 保证改动可被机械化验证，不依赖人工回归

**Non-Goals**

- 不拆分 `chat_service.py`（313 行）、不下沉 SSE 事件定义、不移动 `index_service.py`——这些会改变依赖形状，需要测试网支撑，留给后续变更
- 不改主包名 `backend` → `scipal`（收益是命名语义，代价是触及全仓 import 与部署配置，与结构正确性无关）
- 不引入任何新依赖、不引入 lint/format 工具链
- 不新增测试（测试体系建设是独立的后续变更）

## Decisions

### D1 · `core/auth.py` → `security.py`

**内容**：`hash_password` / `verify_password` / `create_access_token` / `decode_access_token` / `get_current_user`。

**理由**：该文件同时承载"密码学原语"与"FastAPI 鉴权依赖"两类内容。`security` 能同时覆盖两者，且不再与 `routes/auth.py`（HTTP 端点）撞名——这是本次改动中最直接的可读性收益。

**备选**：
- `authn.py`：只强调认证，无法涵盖密码哈希
- `deps.py`：准确描述了 `get_current_user` 的形式，但丢失了语义
- 保持 `core/auth.py`：继续承担同名风险；且 `core` 是误导性目录名（真正的核心在 `backend/domain/`）

### D2 · `api/routes/` → `routes/`

**理由**：`app/api/` 下只有 `routes/` 一个子目录，其 `__init__.py` 为 0 字节。"api → routes" 两层表达的是同一件事。

**备选**：保留 `api/` 以容纳未来的中间件、依赖、异常处理器。但 `main.py` 已经承载了中间件注册，且当前无此类需求——保留空层是为一厢情愿的扩展付费。

### D3 · `schemas/api.py` → `contracts.py`

**理由**：单文件不需要包。名称从"schema"（泛指数据结构）改为"contract"（特指对前端的契约），与该文件的真实角色一致——它是 HTTP 出入口的唯一 DTO 定义处。

**备选**：`schemas/` 是 Pydantic 项目的常见惯例，但惯例服务于多文件包；此处不适用。

### D4 · `services/job_runner.py` → `app/runner.py`

**理由**：`InProcessJobRunner` 与 `main.py` 的 lifespan 同生共死（`runner.start()` → yield → `runner.stop()`），它提供的是**应用运行时**，不是可复用的业务用例。与 `main.py` 并列更能表达这层关系。

**影响**：`main.py` 的唯一一处 import 需更新。

**备选**：留在 `services/`——但会让 `services/` 的语义继续混装"用例"与"运行时设施"。

### D5 · 收口 `routes/sessions.py` 的两个直连端点

**做法**：在 `session_service` 增加 `list_sessions(user_id)` 与 `update_session(session_id, title, is_pinned)` 两个**薄转发函数**（仅透传，不做加工），路由改为调用它们。

**理由**：当前同一文件内 5 个端点有两种风格（3 走 service、2 直连 `storage.sqlite`）。规则一旦有例外，例外就会被复制。收口后 `routes/sessions.py` 内不再存在例外。

**范围说明（实施期补充）**：`routes/auth.py:10` 同样直接引用 `storage.sqlite.users`。但该引用属于认证流程（注册/登录），收口需要先有承载用户仓储的 service——目前并不存在，新建它涉及职责划分决策，超出"纯位移"范围。因此本变更只消除 `sessions` 路由内的例外，`auth` 路由的收口留待后续变更。

**备选**：
- 保留直连：改动量最小，但规则继续存在例外
- 把读取逻辑上移合并进 service：过度设计——storage 返回 `dict` 的契约是稳定的，无需在 service 层重新组装

**注意**：`update_session` 的 NotFound 分支目前在路由内判断（`routes/sessions.py:31-35`），转发后需保持相同的 404 行为。

### D6 · 采用"一次性全量替换"而非"逐个模块迁移"

**理由**：这是纯位移改动。逐个模块迁移会产生"新旧路径混用"的中间态——例如 `routes/chat.py` 已用 `app.contracts` 而 `chat_service.py` 仍用 `app.schemas.api`。中间态无法通过任何静态检查，反而延长了不一致窗口。

一次性替换后，用四项检查一次性收口（见下）。

**备选**：逐模块提交，每步可回滚。但在零测试的前提下，逐步迁移并不比一次性迁移更安全——两者的验证手段相同，而一次性迁移的最终状态更干净。

### D7 · 验证手段设计（因为无测试，验证本身就是设计的一部分）

| # | 检查 | 判定标准 | 能捕获什么 |
|---|---|---|---|
| V1 | 全模块遍历导入 | 94 个模块，0 失败 | 遗漏的 import、循环导入 |
| V2 | `app.openapi()` 路由清单 | 与基线逐条一致（8 条路径） | 路由注册遗漏 |
| V3 | `uv build` 打包 | sdist + wheel 构建成功 | 包结构与打包配置冲突 |
| V4 | 旧路径字符串全仓扫描 | 仓库内不再出现 `app.api.routes` / `app.core.auth` / `app.schemas` / `services.job_runner` | 文档、注释、字符串中的残留引用 |

V4 是关键补充——前三项只覆盖"代码能否运行"，无法发现 README 或注释里留下的死路径。

## Risks / Trade-offs

| 风险 | 缓解 |
|---|---|
| 【遗漏 import】某个文件引用了被移动模块但未被发现 | V1 全模块遍历导入会立即暴露；V4 字符串扫描兜底 |
| 【循环导入】`runner.py` 上移后与 `services` 形成环 | `runner` → `services.ingestion_service` 是单向依赖，后者不反向引用 `runner`，无环。改动后由 V1 验证 |
| 【未预见的外部引用】包外代码引用了被移动路径 | 已核查：唯一跨包引用是 `scipal_eval/cli.py` → `app.services.chat_service`，而 `chat_service` 本变更不移动 |
| 【`__pycache__` 残留】旧路径的 .pyc 文件可能造成误导 | 迁移后清理 `app/` 下的 `__pycache__`；不影响运行时行为 |
| 【IDE 索引失效】重命名后编辑器可能显示旧路径 | 提示：改动后重启语言服务器 |
| 【未来扩展受限】删除 `api/` 层后，若将来要加中间件/依赖层需重新引入 | 可接受：`main.py` 已承载中间件；真需要时再引入有明确理由的层，好过保留一个空层 |

**权衡说明**：本变更收益是**认知成本**（读代码时少一层辨别），而非性能或功能。因此判断标准应是"改动是否真的零风险"，而不是"收益是否足够大"。前者的答案由 V1–V4 四项检查给出。

## Migration Plan

**执行步骤**

1. `git mv` 移动文件（保留文件历史）：`core/auth.py`→`security.py`、`schemas/api.py`→`contracts.py`、`api/routes/`→`routes/`、`services/job_runner.py`→`runner.py`
2. 删除 3 个随目录消失的 `__init__.py`：`app/api/__init__.py`、`app/core/__init__.py`、`app/schemas/__init__.py`。`api/routes/__init__.py` 随目录移动保留为 `routes/__init__.py`（项目内所有包均保留包标记，保持一致性）
3. 全量替换 import 路径（含 `sessions.py` 的收口改动）
4. 清理 `__pycache__`
5. 执行 V1–V4 四项验证，全部通过后提交

**提交粒度**：单个提交。本变更不含逻辑改动，拆分提交只会产生无法验证的中间态。

**回滚策略**：`git revert` 单个提交即可。无数据库迁移、无配置变更、无数据目录变更，回滚不涉及任何持久化影响。

## Open Questions

- 是否要把 V4 的路径扫描固化为 CI 检查（或 pre-commit hook）？——当前无 CI 基础设施，可延后到测试体系落地时一并考虑
- `contracts.py` 未来若超过 200 行是否拆分为 `contracts/` 包？——取决于后续是否引入 OpenAPI codegen；现在决定为时过早
