import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  base: "/liff/",
  plugins: [react()],
  resolve: {
    alias: { "kinsun-shared": path.resolve(__dirname, "../shared") },
  },
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
