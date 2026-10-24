# SciPal 前端

Vue 3 + TypeScript + Vite + Element Plus。负责会话管理、PDF 上传与 SSE 流式问答渲染。

## 快速开始

```bash
npm install
npm run dev        # http://localhost:5173
```

未设置 `VITE_API_BASE_URL` 时，前端使用同源相对路径，由 Vite dev server 把
`/auth`、`/sessions`、`/health` 代理到 `http://127.0.0.1:8000`（可用 `VITE_DEV_PROXY_TARGET` 覆盖）。
需要直连后端时复制 `.env.example` 为 `.env` 并填写绝对地址。

## 脚本

| 命令                              | 说明                          |
| --------------------------------- | ----------------------------- |
| `npm run dev`                     | 启动开发服务器                |
| `npm run build`                   | 类型检查 + 生产构建           |
| `npm run typecheck`               | 仅跑 `vue-tsc`（strict 模式） |
| `npm run lint` / `lint:fix`       | ESLint（TS + Vue 规则）       |
| `npm run format` / `format:check` | Prettier 格式化 / 校验        |

## 目录结构

```
src/
├── api/          # HTTP 层：client（fetch/token/错误）、sse（分帧）、auth/sessions/chat 端点、契约类型
├── components/   # 展示组件（PascalCase）
├── composables/  # 状态与用例：useAuth / useSessionState / useChatStream / usePaperChat
├── constants/    # 常量：app / upload / chat
├── layouts/      # 页面骨架（AppLayout）
├── router/       # 路由与鉴权守卫
├── styles/       # variables / base / layout / element-plus，index.css 为入口
├── types/        # 视图模型（view.ts）
├── utils/        # 纯函数：error / format / markdown
└── views/        # 路由页面（LoginView）
```

## 代码约定

- 命名：组件 PascalCase，组合式函数 `useXxx`，常量 `UPPER_SNAKE_CASE`，布尔值 `is/has/should` 前缀，CSS 类名 BEM。
- 分层：组件只做展示与事件转发；跨组件状态放 composables；HTTP 细节只出现在 `api/`。
- 类型：后端契约类型只放 `api/types.ts`，视图模型只放 `types/view.ts`，禁止重复定义。
- 样式：颜色/阴影/渐变必须使用 `styles/variables.css` 中的 CSS 变量；组件样式一律 `scoped`。
- 事件：用动词短语命名（`createSession`、`requestUpload`、`toggleSearch`），`kebab-case` 绑定。
- 格式：由 Prettier 决定（双引号、分号、100 列），ESLint 不复述格式规则。
