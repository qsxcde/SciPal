## 1. 基线与准备

- [x] 1.1 记录基线：全模块遍历导入的模块总数（预期 94）、`app.openapi()` 的路径清单（预期 8 条）、`app/` 下 4 个待移动模块的引用文件清单
- [x] 1.2 清理 `app/` 下全部 `__pycache__`，避免旧路径的 .pyc 干扰后续验证

## 2. 移动文件（保留 git 历史）

- [x] 2.1 `git mv app/core/auth.py app/security.py`
- [x] 2.2 `git mv app/schemas/api.py app/contracts.py`
- [x] 2.3 `git mv app/api/routes app/routes`（`__init__.py` 随目录保留）
- [x] 2.4 `git mv app/services/job_runner.py app/runner.py`
- [x] 2.5 删除随目录消失的 3 个 `__init__.py`：`app/api/__init__.py`、`app/core/__init__.py`、`app/schemas/__init__.py`
- [x] 2.6 确认 `app/api/`、`app/core/`、`app/schemas/` 三个目录已不存在

## 3. 更新引用

- [x] 3.1 更新 4 个路由文件中的 `backend.app.core.auth` → `backend.app.security`
- [x] 3.2 更新 `routes/chat.py`、`routes/sessions.py`、`services/chat_service.py` 中的 `backend.app.schemas.api` → `backend.app.contracts`
- [x] 3.3 更新 `main.py`：`app.api.routes` → `app.routes`，`app.services.job_runner` → `app.runner`
- [x] 3.4 复核 `app/` 内 docstring 与注释中的路径表述，修正仍指向旧结构的描述

## 4. 收口路由层直连存储

- [x] 4.1 在 `session_service` 新增 `list_sessions(user_id)` 薄转发函数
- [x] 4.2 在 `session_service` 新增 `update_session(session_id, title, is_pinned)` 薄转发函数，未找到时返回 `None`
- [x] 4.3 改写 `routes/sessions.py` 的 `list_sessions` 与 `update_session` 端点改走 service，移除对 `backend.storage.sqlite.sessions` 的直接 import，并保持原有 404 行为

## 5. 验证（V1–V4）

- [x] 5.1 V1 全模块遍历导入：0 失败（模块数 94 → 91，减少量为被删除的三个空壳包，符合预期）
- [x] 5.2 V2 `app.openapi()` 路由清单与 1.1 记录的基线逐条一致（8 条）
- [x] 5.3 V3 `uv build` 成功产出 sdist 与 wheel
- [x] 5.4 V4 全仓扫描确认无 `app.api.routes`、`app.core.auth`、`app.schemas`、`services.job_runner` 的残留引用（含文档与注释）

## 6. 收尾

- [x] 6.1 复核 README 与 `pyproject.toml`：确认入口点 `backend.app.main:main` 与启动命令 `uvicorn backend.app.main:app` 无需变更
- [x] 6.2 清理 `__pycache__`，确认工作树无临时验证产物
- [ ] 6.3 以单个提交完成交付（design.md 要求单提交，避免产生不可验证的中间态；提交动作需用户确认）
