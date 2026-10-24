# 07 前端

目录：`frontend/`
技术栈：Vue 3（`<script setup>` + TS）+ Element Plus + Vite 8 + vue-router（已安装）
状态管理：无 Pinia/Vuex，使用模块级单例 `ref` 的 composables

## 1. 脚本与依赖

`frontend/package.json`：

| 脚本 | 命令 |
|---|---|
| `dev` | `vite`（默认 `http://localhost:5173`） |
| `build` | `vue-tsc -b && vite build` |
| `lint` | `eslint .` |
| `preview` | `vite preview` |

运行时依赖：`vue ^3.5`、`vue-router ^4.6`、`element-plus ^2.12`、`@element-plus/icons-vue`、`markdown-it ^14.2`。
开发依赖：`vite ^8`、`@vitejs/plugin-vue`、`typescript ~6.0`、`vue-tsc`、`eslint`、`typescript-eslint`、`eslint-plugin-vue`。

`vite.config.ts` 只有 `plugins: [vue()]`——**没有 dev server 代理、没有路径别名**。跨域依赖后端 CORS，接口地址由 `VITE_API_BASE_URL` 提供（默认 `http://127.0.0.1:8000`）。

## 2. 目录结构

```
frontend/
├── index.html
├── vite.config.ts
├── package.json
├── .env.example                 # VITE_API_BASE_URL=http://127.0.0.1:8000
├── prototypes/                  # 静态 HTML + 截图设计稿，不参与构建
└── src/
    ├── main.ts                  # 按需注册 Element Plus 组件 + 样式，mount #app
    ├── App.vue                  # 三态：loading / 未登录 / 主界面
    ├── AppLayout.vue            # 页面级编排，唯一调用 usePaperChat()
    ├── index.css                # 全局样式与 CSS 变量
    ├── api.ts                   # HTTP + SSE 客户端 + 后端契约类型
    ├── types.ts                 # 视图模型（反向复用 api.ts 类型）
    ├── router/index.ts          # hash 路由表（当前未注册）
    ├── utils/markdown.ts        # markdown-it token → MarkdownNode 树
    ├── views/LoginView.vue
    ├── composables/
    │   ├── useAuth.ts
    │   ├── useSessionState.ts
    │   ├── useChatStream.ts
    │   └── usePaperChat.ts
    └── components/              # 16 个 SFC
```

## 3. 组件树

```
App.vue
├── LoginView.vue                      (未登录)
└── AppLayout.vue                      (已登录)
    ├── AppSidebar.vue
    │   ├── SidebarHeader.vue
    │   ├── SessionList.vue
    │   │   └── SessionListItem.vue
    │   │       └── SessionActionsMenu.vue
    │   └── RenameSessionDialog.vue
    └── ChatWorkspace.vue
        ├── ChatHeaderBar.vue
        ├── MessageList.vue
        │   └── MessageBubble.vue
        │       ├── MarkdownContent.vue
        │       │   └── MarkdownNodeRenderer.vue
        │       └── MessageActions.vue
        ├── UploadStatusCard.vue
        └── ChatComposer.vue
            └── ComposerTools.vue
```

| 组件 | 职责 | 主要 props / emits |
|---|---|---|
| `App.vue` | 认证门禁 + 骨架屏 | — |
| `LoginView.vue` | 登录/注册切换表单 | 无 props |
| `AppLayout.vue` | 布局编排，向两侧分发事件 | 调用 `usePaperChat()` |
| `AppSidebar.vue` | 侧栏容器（折叠/展开），持有重命名弹窗状态 | props `collapsed, indexedChunks, isUploading, recentSessions, username` |
| `SidebarHeader.vue` | 品牌区 + 新建 + 折叠 | props `collapsed, isBusy`；emits `createSession, toggleCollapse` |
| `SessionList.vue` | 列表滚动容器 | props `collapsed, items` |
| `SessionListItem.vue` | 单条会话 | props `id, title, description, active, collapsed, isPinned` |
| `SessionActionsMenu.vue` | 「⋯」菜单：重命名/置顶/删除 | props `isPinned` |
| `RenameSessionDialog.vue` | 重命名弹窗 | props `visible, initialTitle` |
| `ChatWorkspace.vue` | 对话区容器，转发事件 | 10 个 props |
| `ChatHeaderBar.vue` | 会话标题 + 论文提示 | props `paperHint, sessionTitle` |
| `MessageList.vue` | 空态欢迎页 / 消息列表，滚动跟随（阈值 120/240px） | props `hasPaper, isStreaming, messages, suggestedPrompts` |
| `MessageBubble.vue` | 单条气泡；pending 显示「正在检索论文并生成回答...」 | props `message, pending` |
| `MarkdownContent.vue` | markdown → 安全 VNode 渲染入口 | props `text` |
| `MarkdownNodeRenderer.vue` | 递归渲染 `MarkdownNode` | props `node` |
| `MessageActions.vue` | 复制回答（`navigator.clipboard`） | props `content` |
| `ChatComposer.vue` | 输入框 / 发送 / 选择文件 | props `draft, isStreaming, isUploading, uploadStatus` |
| `ComposerTools.vue` | 工具条按钮（检索开关 / 更多 / 上传），多为 UI 占位 | props `disabled, state` |
| `UploadStatusCard.vue` | 上传/解析/索引进度卡 | props `status` |

Markdown 渲染链：`markdown-it` 解析 → `parseMarkdown()` 生成白名单 `MarkdownNode` 树 → `MarkdownNodeRenderer` 递归渲染，**不使用 `v-html`**。

## 4. 数据流

```
App.vue ──useAuth()──▶ api.getMe / login / register
AppLayout.vue ──usePaperChat()──┬── useSessionState() ──▶ GET/POST/PATCH/DELETE /sessions*
                                └── useChatStream()   ──▶ POST /sessions/{id}/messages (SSE)
```

### 4.1 `useAuth`

模块级单例 `isAuthenticated / user / loading`。`checkAuth()` 在存在 token 时调 `getMe()`，失败 `clearToken()`。登录成功写 `localStorage["scipal_token"]`。

### 4.2 `useSessionState`

持有 `sessions / documents / paperSession / isUploading / uploadStatus`；派生 `hasPaper / displayFileName / indexedChunks`。

上传流程是**轮询**而非 SSE：

```
handleUpload(file)
  → uploadDocument(sessionId, file)          → 202
  → 每 1000ms getSession(sessionId)
        status ready|failed → 结束
        最多 600 次（约 10 分钟）
```

`STATUS_LABELS` 把文档状态映射为中文提示。`DEMO_SESSION_ID = "demo-session"` 用于演示数据。

### 4.3 `useChatStream`

持有 `draft / isStreaming / messages`。

- `sendMessage(text, sessionId)`：先本地乐观插入 user 消息与空 assistant 消息，再消费 `streamChat()`。
- `replaceMessages()`：用会话快照里的持久化消息整体替换。
- `useDemoPaper()`：注入演示消息。
- 重试：`SSE_RETRY_MAX_ATTEMPTS=2`，退避 1s / 2s，每次重试重置累积文本；`AbortError` 直接终止且不报错。
- **只处理 `token` / `sources` / `error` 三类事件，`status` 事件被忽略。**

### 4.4 `usePaperChat`

组合层，对外唯一 API：统一 `errorMessage`、派生 `currentSessionTitle / currentPaperHint`；无会话时自动建会话；`demo-session` 下拦截发送并提示"示例论文仅供预览…"。

## 5. SSE 客户端实现

`src/api.ts` 使用 `fetch` + `res.body.getReader()` + `TextDecoder(..., {stream:true})`，**不用 `EventSource`**（需要 POST 与 `Authorization` 头）。

解析算法：

1. 按 `\n` 切行，保留末尾残行。
2. 以 `data: ` 前缀的行累积到 `dataBuffer`。
3. 空行作为事件边界 → `JSON.parse`；解析失败静默丢弃该帧。
4. `type === "done"` 直接结束生成器。
5. 只消费 `data:` 行，不解析 `event:` / `id:` / `retry:`，不识别 `[DONE]`。

事件联合类型 `MessageChunk`（`api.ts`）：

```ts
| { type: "token"; value: string }
| { type: "sources"; value: SourceRef[] }
| { type: "status"; value: string }
| { type: "error"; value: string }
| { type: "done" }
```

错误处理：非 2xx 时读 `{detail}`，缺失则用中文兜底文案；`res.body` 为空 → 抛"后端没有返回可读取的流式响应"。

## 6. 类型镜像

- 后端契约类型（`SourceRef / PaperDocument / PersistedMessage / RetrievalIndexSummary / SessionSummary / SessionSnapshot / MessageChunk`）定义在 `api.ts`。
- `types.ts` 只放视图模型（`PaperSession / ChatMessageViewModel / SidebarSessionItem / SessionSnapshotViewModel / UploadStatus / ComposerToolState / SuggestedPrompt`），并反向 import `api.ts` 类型。
- **没有共享契约包**，字段为手写 snake_case 镜像；后端改字段前端不会报编译错误。

## 7. 已知问题

1. **路由未注册**：`router/index.ts` 用 `createWebHashHistory` 定义了 `/login` 与 `/`，但 `main.ts` 未 `.use(router)`，`App.vue` 也没有 `<router-view>`。页面切换实际由 `useAuth.isAuthenticated` 驱动，路由表当前是死代码。
2. **`frontend/README.md` 是未清理的 React 模板**，不可作为事实来源。
3. **`status` 事件未消费**：用户看不到"等待索引/检索中/生成中"的细粒度状态，只有 `MessageBubble` 的静态 pending 文案。
4. **无 dev 代理**：本地换后端端口必须改 `frontend/.env` 的 `VITE_API_BASE_URL` 并重启 dev server。
5. **工具条部分按钮是占位**：`ComposerTools` 的检索开关/更多未接后端能力。
6. **上传轮询有上限**：约 10 分钟（600 × 1s）后停止轮询，界面停留在最后一个状态。

## 8. 本地开发

```bash
cd frontend
npm install
cp .env.example .env        # 按需修改 VITE_API_BASE_URL
npm run dev                 # http://localhost:5173
npm run build               # 类型检查 + 产物构建
npm run lint
```

后端需先启动（见 [10 开发与运维](10-development.md)），并确保 `JWT_SECRET_KEY` 的配置与登录方式匹配：

- 未配置 `JWT_SECRET_KEY` 且 `APP_ENV` 为开发类取值：后端处于匿名旁路，数据接口免鉴权，但 `/auth/login`、`/auth/register` 返回 400 `Auth not configured`。前端 `useAuth.checkAuth()` 在无 token 时直接置为未登录态，因此界面会停在 `LoginView` 且无法登录——本地无鉴权联调需要手动写入 `localStorage.setItem("scipal_token", "dev")`。
- `APP_ENV=production` 且缺 `JWT_SECRET_KEY`：数据接口统一 503 `Authentication is not configured`（fail closed）。
- 配置了 `JWT_SECRET_KEY`：走正常注册/登录流程。
