import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { JSDOM } from "jsdom";
import vm from "node:vm";

const appRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const coreRoot = resolve(appRoot, "..", "shared", "otto-pet-core");
const context = {
  console,
  setTimeout,
  clearTimeout,
  AbortController,
  localStorage: { getItem: () => "", setItem: () => undefined },
};
context.window = context;
vm.createContext(context);

for (const name of [
  "anim.js",
  "face.js",
  "emotions.js",
  "behavior.js",
  "sentiment.js",
  "brain.js",
]) {
  vm.runInContext(readFileSync(resolve(coreRoot, name), "utf8"), context, { filename: name });
}

const expectedBlocked = [
  "angry", "furious", "annoyed", "disgusted", "jealous", "suspicious",
  "bored", "sulking", "panic", "shocked", "scared",
];
assert.deepEqual(Array.from(context.PET.BLOCKED_EMOTIONS), expectedBlocked);

// ── theme.ts 的 emotionPolicy 與 renderer 的黑名單必須是同一份 ──────────────
//
// ⚠️ 這兩份清單分屬 App 與 renderer 兩個世界，型別檢查連不起來。任一邊漏改，症狀
// 不是編譯錯誤，而是「阿白某天開始對長輩生氣」——而且只在長輩真的罵它的那一刻
// 才看得到。接手指示第 10 條是 CRITICAL 等級，值得用建置期的閘門守著。
const themeSource = readFileSync(
  resolve(appRoot, "src", "lib", "theme.ts"),
  "utf8",
);
const blockedBlock = themeSource.match(/blocked:\s*\[([\s\S]*?)\]/);
assert.ok(blockedBlock, "theme.ts 找不到 emotionPolicy.blocked");
const themeBlocked = Array.from(blockedBlock[1].matchAll(/"([a-z]+)"/g)).map((m) => m[1]);
assert.deepEqual(
  themeBlocked,
  expectedBlocked,
  "theme.ts 的 emotionPolicy.blocked 與 renderer 的 BLOCKED_EMOTIONS 不一致",
);

// ── assertKeysExist：黑名單的每個 key 都必須真的存在於情緒表 ────────────────
//
// `theme.ts` 宣告了 `assertKeysExist: true` 卻從來沒有人實作這個檢查（驗收報告
// 列為缺失）。放在這裡而不是 runtime：這是 App 給長輩用的，開機 throw 等於整個
// 對講機打不開；建置期擋下來才是對的時機。角色改版把某個情緒改名時，黑名單會
// **安靜失效**——那正是這條要防的。
assert.match(themeSource, /assertKeysExist:\s*true/, "theme.ts 應宣告 assertKeysExist");
for (const key of expectedBlocked) {
  assert.ok(
    context.PET.EMOTION_KEYS.includes(key),
    `黑名單的 ${key} 不存在於 PET.EMOTIONS——角色改版時黑名單會安靜失效`,
  );
}

const localCases = [
  ["你真的很煩", "angry"],
  ["我氣死了", "furious"],
  ["有夠煩", "annoyed"],
  ["好噁心", "disgusted"],
  ["我在吃醋", "jealous"],
  ["這件事很可疑", "suspicious"],
  ["今天好無聊", "bored"],
  ["哼，我不理你", "sulking"],
  ["完蛋了怎麼辦", "panic"],
  ["這太震驚了", "shocked"],
  ["我好害怕", "scared"],
];
for (const [text, matchedEmotion] of localCases) {
  const result = context.PET.senseEmotion(text);
  assert.equal(result.matchedEmotion, matchedEmotion, `本地關鍵詞應先命中 ${matchedEmotion}`);
  assert.equal(result.emotion, "calm", `${matchedEmotion} 必須在命中後被黑名單收斂`);
}

const normalized = context.PET.normalizeBehavior({ emotion: "angry", intensity: 3 });
assert.equal(normalized.primary_emotion, "calm", "LLM 結構化情緒也必須通過同一道黑名單");

const persona = context.PET.buildPersona();
assert.match(persona, /你是「阿白」/);
assert.match(persona, /第一人稱「我」/);
assert.doesNotMatch(persona, /使用者罵你你可能生氣/);

const renderer = readFileSync(resolve(appRoot, "assets", "otto", "renderer.html"), "utf8");
for (const forbidden of [
  "generativelanguage.googleapis.com",
  "getUserMedia",
  "CWA_KEY",
  "localStorage",
  "FoodFinder",
]) {
  assert.equal(renderer.includes(forbidden), false, `renderer 不得包含 ${forbidden}`);
}
assert.match(renderer, /default-src 'none'/);
assert.match(renderer, /data-source="kinsun-bridge\.js"/);

const rendererEvents = [];
const dom = new JSDOM(renderer, {
  runScripts: "dangerously",
  url: "https://kinsun-renderer.invalid/",
  beforeParse(window) {
    window.ReactNativeWebView = {
      postMessage: (message) => rendererEvents.push(JSON.parse(message)),
    };
    window.matchMedia = () => ({ matches: true });
    // DOM 啟動驗證不跑無窮動畫迴圈；正式 WebView 使用原生 requestAnimationFrame。
    window.requestAnimationFrame = () => 1;
    window.cancelAnimationFrame = () => undefined;
  },
});

assert.ok(dom.window.document.querySelector("#petMount svg"), "renderer 應建立 Otto SVG");
assert.equal(rendererEvents.some((event) => event.type === "ready"), true);

dom.window.dispatchEvent(
  new dom.window.MessageEvent("message", {
    data: JSON.stringify({ version: 1, type: "sync", sequence: 1, state: "listening" }),
  }),
);
assert.equal(dom.window.kinsunBear.listening, true);

dom.window.dispatchEvent(
  new dom.window.MessageEvent("message", {
    data: JSON.stringify({
      version: 1,
      type: "sync",
      sequence: 2,
      state: "speaking",
      text: "你真的很煩",
      durationMs: 1200,
    }),
  }),
);
assert.equal(dom.window.kinsunBear.emotionKey, "calm", "WebView 實際接線也必須套黑名單");
assert.equal(dom.window.kinsunBear.talking, true);
dom.window.close();

console.log("Otto renderer 人設、情緒黑名單與離線邊界驗證通過。");
