import js from "@eslint/js";
import globals from "globals";
import pluginVue from "eslint-plugin-vue";
import tseslint from "typescript-eslint";
import prettier from "eslint-config-prettier";
import { defineConfig, globalIgnores } from "eslint/config";

export default defineConfig([
  globalIgnores(["dist", "node_modules"]),
  {
    files: ["**/*.{ts,vue}"],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: {
      globals: globals.browser,
    },
    rules: {
      // TS 已负责未定义标识符检查，no-undef 会误报 DOM 类型
      "no-undef": "off",
      "no-console": ["warn", { allow: ["warn", "error"] }],
      "@typescript-eslint/consistent-type-imports": [
        "error",
        { prefer: "type-imports", fixStyle: "separate-type-imports" },
      ],
    },
  },
  ...pluginVue.configs["flat/recommended"],
  {
    files: ["**/*.vue"],
    languageOptions: {
      parserOptions: {
        parser: tseslint.parser,
      },
    },
  },
  // 业务域边界：features/* 只能向右依赖共用层，不能回头依赖编排层或别的域
  {
    files: ["src/features/**/*.{ts,vue}"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: ["**/layouts/*", "**/views/*", "**/router/*", "**/main"],
              message: "features 不得依赖编排层（layouts/views/router/main）",
            },
            {
              group: ["**/features/*/components/*"],
              message: "features 之间不得跨域引用，改为经 store 或共用 components/ 交互",
            },
          ],
        },
      ],
    },
  },
  // 关闭与 Prettier 冲突的格式规则，格式一律交给 prettier 决定
  prettier,
]);
