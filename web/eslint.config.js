/**
 * web（網頁版全功能前端）的 eslint 設定。
 *
 * 與 frontend/ 同款而非共用一份：兩者是獨立 package，共用會讓其中一邊的
 * 升版牽動另一邊——而 frontend/ 已凍結，不該再被任何變更碰到。
 */

import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    plugins: { "react-hooks": reactHooks, "react-refresh": reactRefresh },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      // 全形空白（U+3000）在中文文案裡是正當排版（AGENTS.md 明訂用全形標點），
      // 預設規則會判成 error——那是假警報，而假警報會訓練人忽略 linter。
      // 只在文案放行，識別字與運算子之間的全形空白仍然抓：那種從來不是刻意的。
      "no-irregular-whitespace": [
        "error",
        { skipStrings: true, skipTemplates: true, skipJSXText: true },
      ],
    },
  },
);
