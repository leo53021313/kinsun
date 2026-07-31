#!/usr/bin/env node
/**
 * 確保 `public/zxing_reader.wasm`（同源提供給長輩端掃碼用）與目前
 * `node_modules/zxing-wasm` 套件版本內附的 wasm 二進位完全一致。
 *
 * 為什麼需要這支腳本：wasm 二進位是手動複製進 `public/` 的靜態檔（見
 * `web/src/talk/qrScanner.ts` 開頭註解），與 `package.json` 宣告的
 * `zxing-wasm` 版本之間沒有任何自動連結。`npm update` 把 glue JS 升到新
 * 版、卻忘記重新複製 wasm 的話，兩者簽章不匹配會在**執行期**以難辨識的
 * 訊息失敗（掃碼完全沒反應），而 CI 的 `tsc`／`vitest`／`vite build` 都
 * 抓不到——因為 TypeScript 不檢查靜態資源內容、測試不碰真的 wasm、
 * build 只是把檔案複製過去，從不比對內容。
 *
 * 用純 Node.js（`fs`／`crypto`）而非 shell 的 `cmp`／`diff`：本專案橫跨
 * Windows／macOS／DGX Spark（AGENTS.md 環境紀律），`cmp` 在 Windows 上
 * 不保證存在。
 */
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const packagedWasmPath = path.join(
  here,
  "..",
  "node_modules",
  "zxing-wasm",
  "dist",
  "reader",
  "zxing_reader.wasm",
);
const servedWasmPath = path.join(here, "..", "public", "zxing_reader.wasm");

function sha256(filePath) {
  return createHash("sha256").update(readFileSync(filePath)).digest("hex");
}

const packagedHash = sha256(packagedWasmPath);
const servedHash = sha256(servedWasmPath);

if (packagedHash !== servedHash) {
  console.error(
    [
      "[verify-wasm] web/public/zxing_reader.wasm 與目前 zxing-wasm 套件版本的 wasm 二進位不一致。",
      "  可能原因：npm update 升級了 zxing-wasm，但忘記重新複製 wasm 二進位。",
      `  套件版本（${packagedWasmPath}）雜湊：${packagedHash}`,
      `  同源靜態檔（${servedWasmPath}）雜湊：${servedHash}`,
      `  修法：cp "${packagedWasmPath}" "${servedWasmPath}"`,
    ].join("\n"),
  );
  process.exit(1);
}

console.log("[verify-wasm] wasm 二進位與 zxing-wasm 套件版本一致。");
