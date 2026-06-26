<p align="center">
  <h1 align="center">SciPal</h1>
  <p align="center">智能论文助手 · Intelligent Paper Assistant</p>
</p>

---

SciPal 是一个面向学术论文阅读场景的 RAG 问答系统。用户上传 PDF 后，系统会在独立会话内完成文档持久化、异步解析、索引构建，并基于论文内容提供带来源引用的中文流式回答。

## 项目特点

- 桌面端 Web 界面，基于 Vue 3 + TypeScript + Element Plus。
- 上传 PDF 后立即返回 `202 Accepted`，文档处理通过后台 job 异步推进。
- 文档状态、任务状态、会话状态显式可见，便于前后端联动和故障恢复。
- 检索索引采用 commit-based snapshot 模型，避免索引构建失败时污染已发布结果。
- 聊天接口基于 SSE 返回 `status`、`token`、`sources`、`done` 事件。
- 回答严格基于论文上下文生成，并附带来源片段信息。

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3 + TypeScript + Element Plus + Vite |
| 后端 API | FastAPI + Pydantic + pydantic-settings |
| PDF 解析 | MinerU |
| Embedding | sentence-transformers |
| 向量检索 | FAISS |
| LLM | DeepSeek，使用 OpenAI Python SDK 调用 |
| 持久化 | SQLite + 会话目录文件存储 |
| 测试 | pytest |

## 系统流程

### 上传与异步处理

`POST /sessions/{id}/documents` 当前采用两阶段流程：

1. 校验会话与上传文件。
2. 保存原始 PDF 到会话目录。
3. 创建 `documents` 记录，初始状态为 `uploaded`。
4. 创建 `jobs` 记录，初始状态为 `queued`。
5. 返回 `202 Accepted`，携带 `document_id`、`job_id`、`document_status`、`job_status`、`session_status`。

后台 `InProcessJobRunner` 会消费排队任务，并在应用启动时恢复上次异常中断的 running job。

### 解析与索引提交

单个文档 ingestion job 会按顺序推进：

1. `uploaded -> parsing`
2. 使用 MinerU 解析 PDF
3. 标准化为 `DocumentIR`
4. 导出 Markdown、质量报告和 chunks
5. `parsed -> chunked -> indexing`
6. 构建 candidate index snapshot
7. 提升为 active ready snapshot
8. 发布当前对外可见的 `retrieval_indexes` 元数据
9. 文档状态更新为 `ready`

如果任一阶段失败，文档会标记为 `failed`，相关 job 和 snapshot 也会同步更新，避免 SQLite 与 FAISS 之间出现状态分裂。

### 聊天与流式回答

`POST /sessions/{id}/messages` 的行为如下：

1. 先持久化 user message。
2. 等待当前会话存在 active ready snapshot。
3. 依次发送 SSE 状态事件：
   - `waiting_for_index`
   - `retrieving`
   - `generating`
4. 基于 active snapshot 对应的 FAISS 索引检索上下文。
5. 调用 DeepSeek 进行中文流式生成。
6. 返回 `sources` 和 `done` 事件，并持久化 assistant message。
7. 若生成中途失败，assistant message 仍会以 `failed` 状态落库，保留已生成内容。

## 快速开始

### 1. 克隆仓库

```bash
git clone <repo-url>
cd 01-SciPal
```

### 2. 配置环境变量

复制并填写 `backend/.env`：

```bash
cp backend/.env.example backend/.env
```

示例配置：

```env
DEEPSEEK_API_KEY=sk-...
EMBEDDING_MODEL=Qwen/Qwen3-Embedding-0.6B
EMBEDDING_MODEL_SOURCE=modelscope
EMBEDDING_AUTO_DOWNLOAD=true
EMBEDDING_DEVICE=cpu
MINERU_TORCH_DEVICE=cpu
MINERU_DISABLE_OCR=true
MINERU_TABLE_ENABLE=true
MINERU_FORMULA_ENABLE=true
MINERU_SHOW_DOWNLOAD_PROGRESS=false
```

说明：

- 当前系统只支持可复制文本 PDF，不处理扫描版或纯图片型 PDF。
- 后端运行数据默认写入 `backend/data/`；部署时可通过 `SCIPAL_DATA_DIR` 覆盖。
- 模型缓存默认写入根级 `data/model_cache/`；部署时可通过 `SCIPAL_MODEL_DIR` 覆盖。
- 通过 `EMBEDDING_MODEL` 指定模型仓库 ID，并用 `EMBEDDING_MODEL_SOURCE` 选择下载源。模型目录从仓库 ID 自动推导；切换模型后请重新建立文档索引，避免 FAISS 中混用不同向量空间。
- 默认按 CPU 配置运行；如果你的本地环境验证通过，也可以自行切换设备配置。
- 如果 MinerU 无法解析当前 PDF，文档状态会持久化为 `failed` 并保留错误信息。

### 3. 安装依赖

后端：

```bash
pip install -r backend/requirements.txt
pip install -r backend/requirements-evals.txt
```

前端：

```bash
cd frontend
npm install
```

### 4. 启动服务

启动后端：

```bash
uvicorn backend.app.main:app --reload
```

启动前端：

```bash
cd frontend
npm run dev
```

默认访问地址：

- 前端：`http://localhost:5173`
- 后端 OpenAPI：`http://localhost:8000/docs`

## 使用方式

1. 打开前端页面。
2. 新建或打开一个会话。
3. 上传论文 PDF。
4. 等待后台 job 完成解析和索引提交。
5. 在聊天框中提问，查看带来源引用的回答。

## 开发与测试

推荐先跑当前后端重构相关的 focused suite：

```bash
pytest tests/test_backend_state_models.py tests/test_document_intake_flow.py tests/test_index_commit_flow.py tests/test_chat_waiting_flow.py tests/test_job_recovery.py tests/test_backend_state_transitions.py tests/test_vector_store.py tests/test_chat_service.py -v
```

## 离线评测

评测说明见 [docs/evaluation/README.md](docs/evaluation/README.md)。

如果你想从现有会话索引导出 bootstrap 评测草稿，可以运行：

```bash
python -m backend.evals.cli generate-draft \
  --session-id session-example \
  --output data/evaluation/drafts/retrieval-v1-draft.jsonl \
  --max-samples 30
```

运行正式评测：

```bash
python -m backend.evals.cli run \
  --dataset data/evaluation/reviewed/retrieval-v1.jsonl \
  --session-id session-example \
  --config-set retrieval-v1 \
  --output-dir eval_outputs/ragas \
  --run-name retrieval-exp-001
```

上述命令默认只执行离线检索评测，不会触发实时 DeepSeek 生成或 RAGAS 调用。需要显式开启时使用：

```bash
python -m backend.evals.cli run \
  --dataset data/evaluation/reviewed/retrieval-v1.jsonl \
  --session-id session-example \
  --config-set retrieval-v1 \
  --output-dir eval_outputs/ragas \
  --run-name retrieval-exp-001-live \
  --with-generation \
  --with-ragas
```

## API 概览

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/sessions` | 创建会话 |
| GET | `/sessions` | 读取会话列表 |
| GET | `/sessions/{id}` | 读取会话快照，包含文档、消息、任务和索引状态 |
| PATCH | `/sessions/{id}` | 更新会话标题或置顶状态 |
| DELETE | `/sessions/{id}` | 归档会话 |
| POST | `/sessions/{id}/documents` | 上传 PDF，返回文档与任务受理状态 |
| POST | `/sessions/{id}/messages` | 发送消息，返回 `text/event-stream` |

## 当前限制

- 当前前端交付范围为 PC Web，不以移动端为目标。
- 当前输入区部分工具按钮仅完成 UI 占位，未对接真实功能。
- 当前解析链路仅支持文本型 PDF。
- 当前检索按单会话、单 active snapshot 组织，尚未扩展到跨论文联合检索。
- 当前问答生成依赖外部模型服务和 embedding 资源可用性。

## License

MIT
