import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const appRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const coreRoot = resolve(appRoot, "vendor", "otto-pet-core");
const outputPath = resolve(appRoot, "assets", "otto", "renderer.html");
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
  const source = read(resolve(coreRoot, name)).replace(/<\/script/gi, "<\\/script");
  return `<script data-source="${name}">\n${source}\n</script>`;
};

const template = read(resolve(coreRoot, "renderer.template.html"));
const css = read(resolve(coreRoot, "renderer.css"));
const html = template
  .replace("/*__OTTO_RENDERER_CSS__*/", css)
  .replace("<!--__OTTO_RENDERER_SCRIPTS__-->", scripts.map(inlineScript).join("\n"));

if (process.argv.includes("--check")) {
  let current = "";
  try {
    current = read(outputPath);
  } catch {
    // 交由下方統一回報 stale，避免把 ENOENT 堆疊當成人看得懂的訊息。
  }
  if (current !== html) {
    console.error("Otto renderer 產物已過期；請執行 npm run bear:build。");
    process.exit(1);
  }
  console.log("Otto renderer 產物與來源一致。");
  process.exit(0);
}

mkdirSync(dirname(outputPath), { recursive: true });
writeFileSync(outputPath, html, "utf8");
console.log(`已產生 ${outputPath}（${Buffer.byteLength(html)} bytes）`);
