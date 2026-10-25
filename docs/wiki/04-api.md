# 04 API 参考

服务入口：`backend/src/backend/main.py` → `app = FastAPI(title="SciPal API")`
本地地址：`http://127.0.0.1:8000`，OpenAPI 文档 `http://127.0.0.1:8000/docs`
契约定义：`backend/src/backend/api/schemas/`（全部 snake_case，无 alias）

## 1. 通用约定

| 项 | 约定 |
|---|---|
| 路径前缀 | **无**统一前缀；仅 auth 路由带 `/auth` |
| 内容类型 | JSON（上传为 `multipart/form-data`，对话为 `text/event-stream`） |
| 鉴权 | `Authorization: Bearer <jwt>`；`OAuth2PasswordBearer(auto_error=False)` |
| 错误体 | FastAPI 默认 `{"detail": "..."}` |
| 状态码 | 仅 `register` 用 201、上传用 202，其余成功均 200 |
| 跨域 | `allow_origin_regex` 默认 `http://(localhost\|127\.0\.0\.1):\d+`，无 credentials |

鉴权行为：

- `JWT_SECRET_KEY` 为空**且** `APP_ENV` ∈ `{development, dev, local, test, testing}`（默认 `development`）→ 开发旁路，`get_current_user` 返回 `{"id": "", "username": "dev"}`，数据接口免鉴权，新建会话的 `sessions.user_id` 写 `NULL`。
- 同一模式下 `/auth/register`、`/auth/login` 返回 `400 Auth not configured`。
- `JWT_SECRET_KEY` 为空但 `APP_ENV` 为其它值（如 `production`）→ 数据接口返回 `503 Authentication is not configured`（fail closed）。
- **资源归属已校验**：`GET/PATCH/DELETE /sessions/{id}`、上传、对话都会比对 `sessions.user_id`；不属于当前用户时统一返回 404（不暴露会话是否存在）。`user_id IS NULL` 的历史会话对所有人可读。`GET /sessions` 仍按 `user_id` 过滤列表。

## 2. 端点总览

| 方法 | 路径 | 用途 | 成功 | 主要错误 |
|---|---|---|---|---|
| GET | `/health` | 存活探针 + 任务线程状态 | 200 | — |
| POST | `/auth/register` | 注册并签发 JWT | 201 | 400 / 409 |
| POST | `/auth/login` | 登录签发 JWT | 200 | 400 / 401 |
| GET | `/auth/me` | 当前用户 | 200 | 401 |
| GET | `/sessions` | 会话列表 | 200 | 401 |
| POST | `/sessions` | 新建会话 | 200 | 401 |
| GET | `/sessions/{id}` | 会话快照 | 200 | 401 / 404 |
| PATCH | `/sessions/{id}` | 改标题 / 置顶 | 200 | 401 / 404 |
| DELETE | `/sessions/{id}` | 归档会话并删磁盘目录 | 200 | 401 |
| GET | `/documents` | 文献库列表（跨会话） | 200 | 401 |
| POST | `/sessions/{id}/documents` | 上传 PDF（异步摄取） | **202** | 400 / 401 / 404 / 413 |
| DELETE | `/sessions/{id}/documents/{document_id}` | 删除文档并重建索引 | 200 | 401 / 404 |
| GET | `/sessions/{id}/documents/{document_id}/content` | 结构化正文（阅读器） | 200 | 401 / 404 |
| GET | `/sessions/{id}/documents/{document_id}/chunks/{chunk_index}` | 引用定位（还原原文段落） | 200 | 401 / 404 |
| POST | `/sessions/{id}/messages` | 流式对话 | 200（SSE） | 401 / 404 |

## 3. 端点详情

### 3.1 `GET /health`

```json
{
  "status": "ok",
  "job_runner": {"running": true, "thread_name": "scipal-job-runner", "stop_requested": false}
}
```

`job_runner` 来自 `InProcessJobRunner.health_status()`，用于确认后台线程存活。

### 3.2 认证

`POST /auth/register` → `201`

```json
// 请求
{"username": "alice", "password": "secret123"}
// 响应
{"token": "<jwt>", "user": {"id": "<uuid>", "username": "alice"}}
```

| 校验 | 失败响应 |
|---|---|
| 未配置 `JWT_SECRET_KEY` | 400 `Auth not configured` |
| 用户名去空格后 < 2 字符 | 400 `Username must be at least 2 characters` |
| 密码 < 6 字符 | 400 `Password must be at least 6 characters` |
| 用户名已存在 | 409 `Username already exists` |

`POST /auth/login` → 200，响应同上；凭据错误 401 `Invalid username or password`。
`GET /auth/me` → `{"id": "...", "username": "..."}`；token 缺失/无效/用户不存在分别 401 `Not authenticated` / `Invalid token` / `User not found`。

JWT 载荷 `{sub: user_id, username, exp}`，算法 `HS256`，有效期 `jwt_expire_minutes`（默认 10080 分钟 = 7 天）。

### 3.3 `GET /sessions`

按 `is_pinned DESC, updated_at DESC` 排序，排除 `is_archived = 1`。响应 `list[SessionSummary]`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | str | 会话 id |
| `title` | str | 标题 |
| `user_id` | str \| null | 归属用户 |
| `created_at` / `updated_at` / `last_opened_at` | str | ISO8601 UTC |
| `is_archived` / `is_pinned` | bool | |
| `document_count` | int | 子查询计数 |
| `message_count` | int | 子查询计数 |
| `indexed_chunks` | int | 子查询计数（chunks 行数） |

### 3.4 `POST /sessions`

无请求体，返回 `{"session_id": "<uuid>"}`。标题初始化为 `msg_default_session_title`。

### 3.5 `GET /sessions/{id}`

返回 `SessionSnapshot`：

| 字段 | 类型 | 说明 |
|---|---|---|
| 基础字段 | | 同 `SessionSummary`（不含三个计数字段） |
| `documents` | `list[DocumentSummary]` | `created_at ASC` |
| `messages` | `list[PersistedMessage]` | `created_at ASC` |
| `status` | `empty\|processing\|ready\|degraded\|failed` | **派生值**，不落库 |
| `jobs` | `list[JobSummary]` | 该会话全部任务 |
| `indexed_chunks` | int | `SELECT count(*) FROM chunks WHERE session_id=?` |
| `active_index` | `IndexSnapshotSummary \| null` | 当前 active ready 快照 |
| `retrieval_index` | `RetrievalIndexSummary \| null` | legacy 兼容的已发布索引行 |

会话不存在、已归档或不属于当前用户 → `404 {"detail": "Session not found"}`。

`DocumentSummary` 关键字段：`id, session_id, filename, file_path, mime_type, file_size, chunk_count, status, error_message, parsed_ir_path, parsed_markdown_path, quality_report_path, parser_name, parser_version, parse_quality_status, created_at, updated_at`。

`JobSummary`：`id, session_id, document_id, type, status, stage, attempt, error_message, created_at, started_at, finished_at`。

`IndexSnapshotSummary`：`id, session_id, status, index_path, chunks_path, document_ids, updated_at, error_message`（`document_ids` 由 `document_ids_json` 反序列化）。

### 3.6 `PATCH /sessions/{id}`

```json
{"title": "Attention 精读", "is_pinned": true}   // 两个字段均可选；传 null 表示不改
```

返回更新后的 `SessionSummary`；不存在 → 404。

### 3.7 `DELETE /sessions/{id}`

`{"status": "deleted"}`。行为：`archive_session`（`is_archived=1`）+ 清理进程内向量库缓存 + 递归删除 `<data>/{raw,parsed,chunks,index}/<session_id>`。**幂等且不泄露**：会话不存在或无权访问时同样返回 200，但不会删除任何数据。

### 3.8 `POST /sessions/{id}/documents`

`multipart/form-data`，字段名固定为 `file`。

```bash
curl -X POST "http://127.0.0.1:8000/sessions/$SID/documents" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@paper.pdf"
```

成功 `202`：

```json
{
  "document_id": "<uuid>",
  "job_id": "<uuid>",
  "document_status": "uploaded",
  "job_status": "queued",
  "session_status": "processing"
}
```

说明：

- `job_status` 声明为 `queued|running`，但创建即 `queued`，实际恒为 `queued`。
- `session_status` 是硬编码 `"processing"`，并非数据库派生值。
- 校验顺序：大小 ≤ `upload_max_bytes`（50 MiB）→ 前 4 字节为 `%PDF` → 会话存在。
- 文件整体读入内存（`file.file.read()`），不做流式落盘。

| 状态码 | detail |
|---|---|
| 400 | `Uploaded file is not a valid PDF`（服务层另有 `Cannot determine file size`，但路由用 `len(bytes)` 兜底，实际不会触发） |
| 404 | `Session not found: <session_id>` |
| 413 | `File too large (max 52428800 bytes)` |

### 3.9 `DELETE /sessions/{id}/documents/{document_id}`

删除单篇论文并重建该会话的索引。

```bash
curl -X DELETE "http://127.0.0.1:8000/sessions/$SID/documents/$DOC" \
  -H "Authorization: Bearer $TOKEN"
```

```json
{"status": "deleted"}
```

说明：

- 依次删除 `chunks` 行、`documents` 行、PDF 与解析产物目录（仅限 data 目录内，越界不删）。
- 随后用剩余 chunks 全量重建索引——FAISS 不支持删除向量，只能重建。
- 会话内已无文档时，快照置为 `failed`、索引元数据置为 `failed`，`/health` 以外的检索会提示重新索引。
- 重建失败同样会把索引置为不可用，宁可要求重新索引，也不让检索命中的是已删除内容。

| 状态码 | detail |
|---|---|
| 404 | `Session not found: <session_id>` |
| 404 | `Document not found: <document_id>` |

### 3.10 `GET /documents`

跨会话的文献库列表，供前端「文献库」页使用。

```bash
curl "http://127.0.0.1:8000/documents" -H "Authorization: Bearer $TOKEN"
```

```json
[
  {
    "document_id": "<uuid>",
    "session_id": "<uuid>",
    "session_title": "新会话",
    "filename": "paper.pdf",
    "status": "ready",
    "chunk_count": 128,
    "file_size": 5242880,
    "parse_quality_status": "good",
    "updated_at": "2026-10-25T12:00:00+00:00"
  }
]
```

说明：

- 已归档会话下的文档不计入。
- 过滤规则与 `domain/access.session_is_accessible` 保持一致：`sessions.user_id IS NULL` 的历史数据对所有调用方可见，其余必须与当前用户匹配。
- 排序：`documents.updated_at DESC, created_at DESC`。
- 开发态匿名（无 JWT）时只返回 `user_id IS NULL` 的会话文档。

| 状态码 | detail |
|---|---|
| 401 | `Not authenticated` |

### 3.11 `GET /sessions/{id}/documents/{document_id}/content`

返回解析后的结构化正文（来自 `document.ir.json`），供阅读器渲染与引用定位。

```bash
curl "http://127.0.0.1:8000/sessions/$SID/documents/$DOC/content" \
  -H "Authorization: Bearer $TOKEN"
```

```json
{
  "document_id": "<uuid>",
  "filename": "paper.pdf",
  "status": "ready",
  "parser_name": "mineru",
  "parse_quality_status": "good",
  "chunk_count": 42,
  "blocks": [
    {
      "id": "b-1",
      "type": "paragraph",
      "text": "The dominant sequence transduction models ...",
      "section_path": ["1", "Introduction"],
      "page_number": 1
    }
  ]
}
```

说明：

- `blocks[].id` 与 SSE `sources[].block_ids` 同源，前端据此滚动到命中段落并高亮。
- 已过滤 `header_footer` 与空文本块，按 `(page_number, reading_order, block_index)` 排序。
- IR 文件缺失或不可读时返回 `blocks: []`，不报错（前端展示"暂无结构化正文"）。
- 按 `(session_id, document_id)` 校验归属，跨会话 404。

| 状态码 | detail |
|---|---|
| 404 | `Session not found: <session_id>` |
| 404 | `Document not found: <document_id>` |

### 3.12 `GET /sessions/{id}/documents/{document_id}/chunks/{chunk_index}`

把回答里的 `sources` 还原为原文段落，供前端「引用即定位」面板使用。

```bash
curl "http://127.0.0.1:8000/sessions/$SID/documents/$DOC/chunks/4" \
  -H "Authorization: Bearer $TOKEN"
```

```json
{
  "document_id": "<uuid>",
  "chunk_index": 4,
  "section": "3 > Method",
  "section_path": ["3", "Method"],
  "page_start": 7,
  "page_end": 8,
  "type": "paragraph",
  "text": "<完整 chunk 正文，非 excerpt>",
  "block_ids": ["b-12", "b-13"]
}
```

说明：

- 按 `(session_id, document_id, chunk_index)` 唯一命中，跨会话返回 404，避免用 document_id 横向越权。
- 返回 `chunks.text_content`（全文），而 SSE `sources[].text_excerpt` 只有 220 字符摘要。
- 引用里的 `paper_id` 即 `document_id`；历史消息缺 `paper_id` 时前端只展示 excerpt。

| 状态码 | detail |
|---|---|
| 404 | `Session not found: <session_id>` |
| 404 | `Source chunk not found: document=<id> chunk=<n>` |

### 3.13 `POST /sessions/{id}/messages`（SSE）

```json
{"role": "user", "content": "这篇论文的核心贡献是什么？", "regenerate": false}
```

`role` 默认 `"user"`，服务端只使用 `content` 与 `regenerate`，不校验也不落库传入的 `role`。

`regenerate: true` 时复用上一条提问：先删除末尾的 assistant 消息，再把该提问排除出对话历史后重新生成；若末尾不是 assistant 消息，则退化为普通提问。

客户端中断（关闭页面 / 点「停止生成」）时，已生成的部分以 `status="stopped"` 落库，避免刷新后本轮回答凭空消失。

响应头 `Content-Type: text/event-stream`。会话不存在或无权访问时在建流之前返回 `404 Session not found`；建流成功后的业务错误通过事件表达，HTTP 状态恒为 200。

## 4. SSE 协议

编码方式（`routes/chat.py:22-23`）：

```
data: {"type":"...","value":...}\n\n
```

只使用 `data:` 行，**不使用** `event:` / `id:` / `retry:`；事件类型由 JSON 的 `type` 字段区分，空行作为事件边界。

| type | value | 说明 |
|---|---|---|
| `status` | `waiting_for_index` \| `retrieving` \| `generating` | 阶段提示 |
| `token` | string | 增量文本 |
| `sources` | `list[SourceRef]` | 引用来源 |
| `warning` | string | 非致命告警（如无有效引用） |
| `error` | string | 错误文案 |
| `done` | 无 `value` | 结束哨兵 |

`SourceRef` 字段：`paper_id?`、`section`、`chunk_index`、`text_excerpt?`、`page_start?`、`page_end?`、`block_ids?`、`confidence?`。

### 4.1 正常时序

```
status:waiting_for_index   ← 仅当首轮无 ready 快照时发出（延迟到索引就绪后再发）
status:retrieving
status:generating
token × N
warning                    ← 引用校验不通过时
sources
done
```

assistant 消息在 `done` 之前落库，因此客户端收到 `done` 后立刻 `GET /sessions/{id}` 能读到完整回答。

### 4.2 异常时序

| 场景 | 事件序列 | 落库状态 |
|---|---|---|
| 索引等待超时（`index_max_wait=10s`） | `status:waiting_for_index` → `token`（`msg_index_not_ready`）→ `sources:[]` → `done` | assistant `status=failed` |
| 生成中途异常 | `error:"生成失败，请重试。"` → `done` | 已生成内容以 `status=failed` 保存 |
| 路由层兜底异常 | `error:"internal_error"` → `done` | 视异常发生阶段 |
| 检索为空 | `token`（`msg_empty_retrieval`）→ `sources:[]` → `done` | assistant `status=complete` |
| 客户端断开 | 无（服务端只记日志） | 视阶段 |

调用示例：

```ts
const res = await fetch(`${API_BASE}/sessions/${sid}/messages`, {
  method: "POST",
  headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
  body: JSON.stringify({ role: "user", content: "论文用了什么数据集？" }),
});
const reader = res.body!.getReader();
const decoder = new TextDecoder();
let buffer = "";
while (true) {
  const { value, done } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });
  const frames = buffer.split("\n\n");
  buffer = frames.pop() ?? "";
  for (const frame of frames) {
    const line = frame.split("\n").find((l) => l.startsWith("data: "));
    if (!line) continue;
    const event = JSON.parse(line.slice(6));
    if (event.type === "done") return;
  }
}
```

## 5. 未暴露 HTTP 的能力

`evaluation.evaluate_session_chat` / `evaluation.evaluate_session_retrieval` **没有对应路由**，仅供 `scipal_eval` CLI 在进程内调用（见 [09 离线评测](09-evaluation.md)）。

## 6. 联调注意点

1. 全部字段为 snake_case，前端 `api.ts` 是手工镜像，后端改名会静默导致前端字段为 `undefined`。
2. `status` 事件前端当前未消费（见 [07 前端](07-frontend.md)），联调时以服务端日志为准。
3. 上传接口返回很快，但文档 `ready` 前发起对话会触发最长 10s 的索引等待。
4. `DELETE /sessions/{id}` 会真的删掉磁盘产物，无法通过重新打开恢复。
