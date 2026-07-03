import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// 觀測後台入口：root 指向 admin/，建置產物與 LIFF 端分離。
export default defineConfig({
  root: "admin",
  base: "/admin/",
  plugins: [react()],
  build: {
    outDir: "../dist-admin",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
