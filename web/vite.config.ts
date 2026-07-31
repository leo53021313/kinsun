import path from "node:path";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  // 靜態檔由 FastAPI 掛在 /demo（同源，免 CORS——後端沒有 CORS middleware，
  // 跨網域一定失敗）。base 要與掛載路徑一致，否則資產路徑會 404。
  base: "/demo/",
  plugins: [react(), tailwindcss()],
  // 測試設定併入本檔而非另開一份：alias 只有一份才不會漂移（同 frontend/ 的做法）。
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    globals: true,
    // ⚠️ Vitest 預設 include 為 `**/*.{test,spec}.?(c|m)[jt]s?(x)`、預設 exclude 只有
    // node_modules／.git——`e2e/journey.spec.ts`（Playwright）會被這個萬用字元一併
    // 撿走，用 vitest 的 test runner 執行 Playwright 的 `test()`/`page` fixture 必然
    // 整批炸掉（`page` 從未被注入）。E2E 走獨立的 `npm run e2e`（playwright test），
    // 不進 `vitest run`。
    exclude: ["**/node_modules/**", "**/.git/**", "e2e/**"],
  },
  resolve: {
    alias: {
      "kinsun-shared": path.resolve(import.meta.dirname, "../shared"),
      "@": path.resolve(import.meta.dirname, "src"),
    },
  },
  server: {
    port: 5174,
    // 開發時打真後端。5173 給 frontend/、5273 給 Opik，故本專案用 5174。
    proxy: { "/api": "http://localhost:8000" },
  },
});
