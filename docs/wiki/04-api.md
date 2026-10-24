# 04 API 参考

服务入口：`backend/src/backend/app/main.py` → `app = FastAPI(title="SciPal API")`
本地地址：`http://127.0.0.1:8000`，OpenAPI 文档 `http://127.0.0.1:8000/docs`
契约定义：`backend/src/backend/app/contracts.py`（全部 snake_case，无 alias）

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

- `JWT_SECRET_KEY` 为空（默认）→ 开发旁路，`get_current_user` 直接返回 `{"id": "", "username": "dev"}`，数据接口免鉴权，`sessions.user_id` 写 `NULL`。
- 同一模式下 `/auth/register`、`/auth/login` 返回 `400 Auth not configured`。
- 资源归属**未校验**：知道 `session_id` 即可读/改/删/上传/对话，仅 `GET /sessions` 按 `user_id` 过滤。多用户部署前必须补归属校验。

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
| POST | `/sessions/{id}/documents` | 上传 PDF（异步摄取） | **202** | 400 / 401 / 404 / 413 |
| POST | `/sessions/{id}/messages` | 流式对话 | 200（SSE） | 401 |

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

会话不存在或已归档 → `404 {"detail": "Session not found"}`。

`DocumentSummary` 关键字段：`id, session_id, filename, file_path, mime_type, file_size, chunk_count, status, error_message, parsed_ir_path, parsed_markdown_path, quality_report_path, parser_name, parser_version, parse_quality_status, created_at, updated_at`。

`JobSummary`：`id, session_id, document_id, type, status, stage, attempt, error_message, created_at, started_at, finished_at`。

`IndexSnapshotSummary`：`id, session_id, status, index_path, chunks_path, document_ids, updated_at, error_message`（`document_ids` 由 `document_ids_json` 反序列化）。

### 3.6 `PATCH /sessions/{id}`

```json
{"title": "Attention 精读", "is_pinned": true}   // 两个字段均可选；传 null 表示不改
```

返回更新后的 `SessionSummary`；不存在 → 404。

### 3.7 `DELETE /sessions/{id}`

`{"status": "deleted"}`。行为：`archive_session`（`is_archived=1`）+ 清理进程内向量库缓存 + 递归删除 `<data>/{raw,parsed,chunks,index}/<session_id>`。**幂等**：会话不存在也返回 200。

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
| 404 | `Session not found. Please create a session first.` |
| 413 | `File too large (max 50MB)` |

### 3.9 `POST /sessions/{id}/messages`（SSE）

```json
{"role": "user", "content": "这篇论文的核心贡献是什么？"}
```

`role` 默认 `"user"`，当前服务端**只使用 `content`**，不校验也不落库传入的 `role`。

响应头 `Content-Type: text/event-stream`，HTTP 状态恒为 200（业务错误也通过事件表达）。

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

`chat_service.evaluate_session_chat` / `evaluate_session_retrieval` **没有对应路由**，仅供 `scipal_eval` CLI 在进程内调用（见 [09 离线评测](09-evaluation.md)）。

## 6. 联调注意点

1. 全部字段为 snake_case，前端 `api.ts` 是手工镜像，后端改名会静默导致前端字段为 `undefined`。
2. `status` 事件前端当前未消费（见 [07 前端](07-frontend.md)），联调时以服务端日志为准。
3. 上传接口返回很快，但文档 `ready` 前发起对话会触发最长 10s 的索引等待。
4. `DELETE /sessions/{id}` 会真的删掉磁盘产物，无法通过重新打开恢复。
