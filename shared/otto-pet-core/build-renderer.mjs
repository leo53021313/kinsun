/**
 * 由 `shared/otto-pet-core/` 的白名單來源產生單檔 renderer.html。
 *
 * ⚠️ 兩端各留一份產物，而不是共用一個路徑：Expo 要它在 `app/assets/` 底下才進得了
 * bundle，Vite 要它在 `web/public/` 底下才服務得到靜態檔。來源只有一份，產物由這支
 * 腳本同時寫出兩份，`--check` 兩份都驗——漂掉的時候會在 CI 紅，不會等到 demo 當天
 * 才發現兩邊的阿白不一樣。
 *
 * ⚠️ 這支刻意零依賴（只用 node 內建），才能住在 `shared/` 而不必替共用包裝
 * node_modules。需要 jsdom 的實際啟動驗證留在 `app/scripts/test-otto-runtime.mjs`。
 */

import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const coreRoot = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(coreRoot, "..", "..");
const outputs = [
  resolve(repoRoot, "app", "assets", "otto", "renderer.html"),
  resolve(repoRoot, "web", "public", "otto", "renderer.html"),
];
const scripts = [
  "bear_svg.js",
  "visemes.js",
  "anim.js",
  "rig.js",
  "body.js",
  "face.js",
  "fx_art.js",
  "fx.js",
  "emotions.js",
  "motion.js",
  "behavior.js",
  "quality.js",
  "pet.js",
  "idle.js",
  "lipsync.js",
  "sentiment.js",
  "kinsun-bridge.js",
];

const read = (path) => readFileSync(path, "utf8").replace(/\r\n/g, "\n");
const inlineScript = (name) => {
  const source = read(resolve(coreRoot, name)).replace(/<\/script/gi, "<\/script");
  return `<script data-source="${name}">\n${source}\n</script>`;
};

const template = read(resolve(coreRoot, "renderer.template.html"));
const css = read(resolve(coreRoot, "renderer.css"));
const html = template
  .replace("/*__OTTO_RENDERER_CSS__*/", css)
  .replace("<!--__OTTO_RENDERER_SCRIPTS__-->", scripts.map(inlineScript).join("\n"));

if (process.argv.includes("--check")) {
  const stale = outputs.filter((outputPath) => {
    let current = "";
    try {
      current = read(outputPath);
    } catch {
      // 交由下方統一回報 stale，避免把 ENOENT 堆疊當成人看得懂的訊息。
    }
    return current !== html;
  });
  if (stale.length > 0) {
    console.error(`Otto renderer 產物已過期：\n  ${stale.join("\n  ")}\n請執行 npm run bear:build。`);
    process.exit(1);
  }
  console.log(`Otto renderer 產物與來源一致（${outputs.length} 份）。`);
  process.exit(0);
}

for (const outputPath of outputs) {
  mkdirSync(dirname(outputPath), { recursive: true });
  writeFileSync(outputPath, html, "utf8");
  console.log(`已產生 ${outputPath}（${Buffer.byteLength(html)} bytes）`);
}
