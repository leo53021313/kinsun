#!/usr/bin/env node
/**
 * 確保 `web/src/elder/countyCoords.ts` 的 `COUNTY_COORDS` 與後端
 * `src/kinsun/tools/weather.py::_COUNTY_COORDS` 逐鍵一致。
 *
 * 為什麼需要這支腳本：兩份表分屬 Python／TypeScript 兩個執行環境，沒有辦法
 * 共用同一份原始碼，只能各自複製一份字面值（見 `countyCoords.ts` 檔頭）。
 * `npm update`／後端修正某縣市座標時忘記同步另一邊，兩份表就會悄悄漂移——
 * `tsc`／`vitest`／`vite build` 都抓不到，因為兩邊各自語法正確、各自的測試
 * 只驗自己那份，沒有人比對過彼此。做法比照 `verify-wasm-checksum.mjs` 防
 * wasm 二進位漂移的精神：不靠人記得，靠建置擋下來。
 *
 * 用純 Node.js 的正規表示式解析兩份原始碼（不執行 Python、不編譯 TypeScript）：
 * 本專案橫跨 Windows／macOS／DGX Spark（AGENTS.md 環境紀律），不能假設執行
 * 環境裝了 Python 或能跑 ts-node；純文字解析兩邊都能跑。
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const pythonPath = path.join(here, "..", "..", "src", "kinsun", "tools", "weather.py");
const tsPath = path.join(here, "..", "src", "elder", "countyCoords.ts");

/**
 * 從原始碼裡截出「一個字典／物件字面值」的本體：找到 `anchor` 之後的第一個
 * `{`，配對到與它同一層級的 `}` 為止（考慮巢狀括號，雖然這兩份表目前都沒有
 * 巢狀，仍寫成通用版本以免未來改動格式時腳本悄悄失效）。
 */
function extractBraceBlock(source, anchor, label) {
  const anchorIndex = source.indexOf(anchor);
  if (anchorIndex === -1) {
    console.error(`[verify-county-coords] ${label} 找不到 "${anchor}"，表結構可能已改名。`);
    process.exit(1);
  }
  const openIndex = source.indexOf("{", anchorIndex);
  let depth = 0;
  for (let i = openIndex; i < source.length; i += 1) {
    if (source[i] === "{") depth += 1;
    if (source[i] === "}") {
      depth -= 1;
      if (depth === 0) {
        return source.slice(openIndex + 1, i);
      }
    }
  }
  console.error(`[verify-county-coords] ${label} 的括號沒有正常配對，表結構可能已改壞。`);
  process.exit(1);
  return "";
}

/** 逐行解析 `"名稱": (數字, 數字)` 或 `"名稱": [數字, 數字]` 這種條目，回傳 Map。 */
function parseEntries(block, label) {
  const entryPattern = /"([^"]+)"\s*:\s*[([]\s*([\d.]+)\s*,\s*([\d.]+)\s*[)\]]/g;
  const entries = new Map();
  for (const match of block.matchAll(entryPattern)) {
    const [, name, latText, lonText] = match;
    entries.set(name, [Number(latText), Number(lonText)]);
  }
  if (entries.size === 0) {
    console.error(`[verify-county-coords] ${label} 解析不到任何條目，正規表示式可能與新格式不合。`);
    process.exit(1);
  }
  return entries;
}

const pythonSource = readFileSync(pythonPath, "utf8");
const tsSource = readFileSync(tsPath, "utf8");

const pythonBlock = extractBraceBlock(pythonSource, "_COUNTY_COORDS = {", "後端 weather.py");
const tsBlock = extractBraceBlock(tsSource, "export const COUNTY_COORDS", "web countyCoords.ts");

const pythonEntries = parseEntries(pythonBlock, "後端 weather.py");
const tsEntries = parseEntries(tsBlock, "web countyCoords.ts");

const allNames = new Set([...pythonEntries.keys(), ...tsEntries.keys()]);
const mismatches = [];

for (const name of allNames) {
  const pythonValue = pythonEntries.get(name);
  const tsValue = tsEntries.get(name);
  if (pythonValue === undefined) {
    mismatches.push(`「${name}」只存在於 web/countyCoords.ts，後端 weather.py 沒有這一筆。`);
    continue;
  }
  if (tsValue === undefined) {
    mismatches.push(`「${name}」只存在於後端 weather.py，web/countyCoords.ts 沒有這一筆。`);
    continue;
  }
  const [pyLat, pyLon] = pythonValue;
  const [tsLat, tsLon] = tsValue;
  // 兩邊都是同一組小數字面值逐字複製，容許極小誤差只是防浮點解析的雜訊，
  // 不是要放寬「座標可以不一樣」。
  const epsilon = 1e-9;
  if (Math.abs(pyLat - tsLat) > epsilon || Math.abs(pyLon - tsLon) > epsilon) {
    mismatches.push(
      `「${name}」座標不一致：後端 (${pyLat}, ${pyLon})，web (${tsLat}, ${tsLon})。`,
    );
  }
}

if (mismatches.length > 0) {
  console.error(
    [
      "[verify-county-coords] web/src/elder/countyCoords.ts 與後端",
      "  src/kinsun/tools/weather.py::_COUNTY_COORDS 的縣市座標表已經漂移：",
      ...mismatches.map((line) => `  - ${line}`),
      "  這張表若要新增、刪除或修改任何一個縣市，兩邊必須同一個 commit 一起改",
      "  （見 countyCoords.ts 檔頭說明）。",
    ].join("\n"),
  );
  process.exit(1);
}

console.log(
  `[verify-county-coords] 縣市座標表一致（共 ${allNames.size} 縣市，web 與後端逐鍵比對通過）。`,
);
