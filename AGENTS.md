# 仓库指南

## 项目结构与模块组织
SciPal 由 Python 后端和 Vue 前端组成。后端代码位于 `backend/`：FastAPI 路由在 `backend/app/api/routes`，业务服务在 `backend/app/services`，RAG 的解析、检索和生成逻辑在 `backend/rag`，持久化代码在 `backend/storage`，提示词在 `backend/prompts`，YAML 配置在 `backend/configs`。前端代码位于 `frontend/src`，组件在 `frontend/src/components`，组合式函数在 `frontend/src/composables`，静态资源在 `frontend/public`。测试集中放在 `tests/`。项目说明和评测文档在 `docs/`，已生成的评测结果在 `eval_outputs/`。

## 构建、测试与本地开发命令
在仓库根目录安装后端依赖：

```bash
pip install -r backend/requirements.txt
pip install -r backend/requirements-evals.txt
```

启动后端 API：

```bash
uvicorn backend.app.main:app --reload
```

前端命令需在 `frontend/` 目录下运行：

```bash
npm install        # 安装 Vue/Vite 依赖
npm run dev        # 启动 Vite 开发服务器
npm run build      # 类型检查并构建生产产物
npm run lint       # 运行 ESLint
npm run preview    # 预览生产构建
```

在仓库根目录使用 `pytest` 运行测试；例如 `pytest tests/test_chat_service.py -v` 可运行单个测试文件。

## 编码风格与命名约定
Python 使用 4 空格缩进；模块、函数和变量使用 snake_case；必要时补充类型标注。FastAPI 路由处理函数应保持轻量，将工作流逻辑放入 service 或 `backend/rag` 模块。TypeScript/Vue 遵循现有 `.vue` 文件风格；组件使用 PascalCase，组合式函数命名为 `useThing.ts`，共享类型放在 `frontend/src/types.ts`。修改前端后请运行 `npm run lint`。

## 测试指南
测试框架为 pytest，`pytest.ini` 中设置了 `pythonpath = .`。测试文件命名为 `test_*.py`，共享 fixture 放在 `tests/conftest.py`。修改后端状态流转、文档解析、检索、存储或评测逻辑时，应补充对应的聚焦测试。除非评测命令明确需要，否则避免在单元测试中依赖真实模型或网络调用。

## 提交与 Pull Request 规范
当前 Git 历史采用简短的 Conventional Commit 风格前缀，例如 `feat:`、`fix:`、`test:` 和 `revert:`。提交信息应使用祈使语气，并聚焦单一变更。Pull Request 需要说明行为变化、列出验证命令、关联相关 issue 或文档；涉及前端可见变化时，请附截图或录屏。

## 安全与配置提示
不要提交 `.env`、`data/`、`backend/data/`、SQLite 数据库、模型缓存或 API key。密钥和本地配置应写入 `backend/.env`；常用项包括 `DEEPSEEK_API_KEY`、embedding 配置以及 MinerU 缓存和设备选项。切换 embedding 模型后，应重建相关索引，避免混用不同向量空间。
