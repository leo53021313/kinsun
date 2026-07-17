/**
 * frontend（LIFF ＋ 觀測後台）的 eslint 設定。
 *
 * 刻意不與 app/ 共用設定：app/ 是 React Native、frontend/ 是瀏覽器 Vite app，
 * 執行環境與慣例本就不同。實測顯示共用會製造假警報（通用設定看不懂 RN 載入
 * 資產的 require()），而假警報會訓練人忽略 linter。
 */

import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "dist-admin"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      // react-hooks v7 的 Compiler 層：除了經典的 rules-of-hooks／exhaustive-deps，
      // 另抓 set-state-in-effect（effect 裡同步 setState 會觸發連鎖重繪）與
      // refs（render 期間改 ref）。frontend 沒跑 React Compiler（React 18 ＋ Vite），
      // 但連鎖重繪在 React 18 一樣是真的效能問題，且與 app/ 同標準有其價值。
      ...reactHooks.configs.recommended.rules,
      // Vite HMR 要求元件檔只匯出元件，否則熱更新會整頁重載。
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      // 全形空白（U+3000）在中文文案裡是正當排版，AGENTS.md 也明訂用全形標點——
      // 預設規則會把它判成 error，那是假警報，而假警報會訓練人忽略 linter。
      //
      // 只在「文案」放行（模板字串、畫面文字），「程式碼」裡仍然抓：識別字或
      // 運算子之間冒出全形空白從來不是刻意的，那種才是這條規則要防的 bug。
      // skipStrings 預設已為 true，寫出來是為了讓三個情境一目了然、不必查文件。
      "no-irregular-whitespace": [
        "error",
        { skipStrings: true, skipTemplates: true, skipJSXText: true },
      ],
    },
  },
);
