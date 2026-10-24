import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

const BACKEND_ORIGIN = process.env.VITE_DEV_PROXY_TARGET ?? "http://127.0.0.1:8000";

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    // 未设置 VITE_API_BASE_URL 时，前端走同源相对路径，由 dev server 代理到后端
    proxy: {
      "/auth": BACKEND_ORIGIN,
      "/sessions": BACKEND_ORIGIN,
      "/health": BACKEND_ORIGIN,
    },
  },
  build: {
    // Element Plus 体积较大，单独成 chunk 便于长期缓存
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules/element-plus") || id.includes("@element-plus")) {
            return "vendor-element";
          }
          if (id.includes("node_modules/vue") || id.includes("node_modules/@vue")) {
            return "vendor-vue";
          }
          return undefined;
        },
      },
    },
  },
});
