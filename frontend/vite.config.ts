import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  base: "/liff/",
  plugins: [react()],
  // 測試設定併入既有 config 而非另開一份：kinsun-shared 的 alias 已在下方 resolve
  // 中，複用即為單一真相；另開設定檔就得維護兩份會漂移的 alias。
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    globals: true,
  },
  resolve: {
    alias: { "kinsun-shared": path.resolve(__dirname, "../shared") },
  },
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
