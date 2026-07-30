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
  },
  resolve: {
    alias: {
      "kinsun-shared": path.resolve(__dirname, "../shared"),
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    port: 5174,
    // 開發時打真後端。5173 給 frontend/、5273 給 Opik，故本專案用 5174。
    proxy: { "/api": "http://localhost:8000" },
  },
});
