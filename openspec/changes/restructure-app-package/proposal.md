## Why

`app/` 包存在四处结构性错位。它们都不是行为缺陷，而是持续消耗认知成本的"目录名不指向真相"：

1. **三个 0 字节空壳包**（`app/api/`、`app/api/routes/`、`app/core/`）——层级没有换来任何封装价值
2. **一对同名 `auth.py`**——`core/auth.py` 是安全机制，`routes/auth.py` 是 HTTP 端点；说"改一下 auth"时必须先问是哪个
3. **`services/` 混装两种性质的东西**——业务服务（chat/document/ingestion/session）与运行时调度器（`job_runner`，由 `main.py` 的 lifespan 启停）混在一起
4. **两个路由端点绕过 service 直连存储**——`routes/sessions.py` 内 5 个端点里 2 个直连 `storage.sqlite`，"路由不碰 DB"的规则存在例外

同类问题还有一处命名误导：`app/schemas/api.py` 是单文件却占用一个包；`core` 这个目录名暗示"核心领域"，而真正的核心在 `backend/domain/`。

这些问题的共同特征是：**修正它们是纯机械位移，但收益真实**——改完后 `app/` 的每一层都能用一句话说清职责。

## What Changes

- **删除** 3 个随目录消失的 `__init__.py`：`app/api/__init__.py`、`app/core/__init__.py`、`app/schemas/__init__.py`（`app/api/routes/__init__.py` 随目录移动，保留为 `app/routes/__init__.py`）
- **展平** `app/api/routes/` → `app/routes/`，移除一层无封装价值的嵌套
- **改名** `app/core/auth.py` → `app/security.py`，消除与 `app/routes/auth.py` 的同名冲突；该文件的内容是安全机制（bcrypt、JWT、`get_current_user` 依赖），`security` 比 `auth` 更准确
- **改名** `app/schemas/api.py` → `app/contracts.py`，单文件不再占包，名称直指其职责（HTTP 契约的唯一出口）
- **迁出** `app/services/job_runner.py` → `app/runner.py`，与 `main.py` 的 lifespan 同处一层
- **收口** `app/routes/sessions.py` 中 `list_sessions` 与 `update_session` 两个端点，改为经由 `session_service` 转发，使分层规则无例外
- **同步** 更新全部 import 路径与文档引用

明确不变的部分：HTTP 端点集合与路径、请求/响应格式、SSE 事件类型与序列、数据库 schema、数据目录布局、全部运行时行为。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。

本变更为纯结构重排，不改变任何 spec 级行为（端点契约、状态机、持久化格式均不变），因此按 schema 约定在 `.openspec.yaml` 中标记 `skip_specs: true`，不产出 delta spec。

## Impact

**受影响代码**：`app/` 包内全部 19 个文件。影响面经引用核查后确认**完全封闭在包内**：

| 待移动模块 | 引用方 | 引用方数量 |
|---|---|---|
| `app.core.auth` | `app/routes/` 下 4 个路由文件 | 4（全部包内） |
| `app.schemas` | 2 个路由 + `services/chat_service.py` | 3（全部包内） |
| `services.job_runner` | `app/main.py` | 1（包内） |
| `app.api.routes` | `app/main.py` | 1（包内） |

**不受影响**：

- `scipal_eval/cli.py` 确实引用了 `app.services`，但目标是 `chat_service` 的评测函数，而 `chat_service` 本变更不移动
- `pyproject.toml` 的入口点 `scipal-backend = "backend.app.main:main"` 与 README 的 `uvicorn backend.app.main:app` 均不涉及被移动文件（`main.py` 位置不变）
- 无 API 变更、无依赖变更、无配置变更、不触及数据库与数据目录

**验证方式**：全模块遍历导入（当前 94 个模块，期望 0 失败）+ `uv build` 打包 + `app.openapi()` 路由清单比对。

**与他变更的关系**：本变更是后续"依赖重构"（拆分 `chat_service`、下沉 SSE 事件定义、`index_service` 迁入 `rag/indexing`、领域模型下沉至 `domain`）的前置位移，但两者不耦合，可独立交付与回滚。
