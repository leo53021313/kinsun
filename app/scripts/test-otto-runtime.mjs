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

// ── 依情緒推導的手部動作（2026-08-16）──────────────────────────────────────
//
// ⚠️ 另開一顆 DOM 而不是沿用上面那顆：上面的 `requestAnimationFrame` 是 `() => 1`
// （刻意不跑無窮動畫迴圈），而手勢是 procedural 的——不推進動畫幀就什麼都量不到。
//
// 這一段守的是「手勢會不會被自己的收尾流程吃掉」：手勢只在 `action`／`emotion`
// 狀態取樣，由 `talkEnd()` 在最後一個字之後切進去；而對講機是「音檔播完 → 佇列空
// → 立刻送 idle」，兩件事幾乎同時。沒有 `GESTURE_HOLD_MS` 那道保護的話，實測右肩
// 擺幅會由 22.5 掉到 1.99——阿白看起來從頭到尾沒有手。
{
  const gestureFrames = [];
  const gestureDom = new JSDOM(renderer, {
    runScripts: "dangerously",
    url: "https://kinsun-renderer.invalid/",
    beforeParse(window) {
      window.matchMedia = () => ({ matches: false });
      window.requestAnimationFrame = (cb) => gestureFrames.push(cb);
      window.cancelAnimationFrame = () => undefined;
      window.ReactNativeWebView = { postMessage: () => undefined };
    },
  });

  // ⚠️ 時鐘必須**跨呼叫**單調遞增：每次都從 performance.now() 重新起算的話，真實
  // 時間幾乎沒走，於是每次的第一幀 dt 是負數（pet.js 的 `now - this._last`），動畫
  // 會倒退、待機的倒數計時被加回去。
  let clock = gestureDom.window.performance.now();
  const advance = (n) => {
    for (let i = 0; i < n; i += 1) {
      clock += 16;
      for (const cb of gestureFrames.splice(0)) cb(clock);
    }
  };
  const sync = (sequence, state, extra = {}) =>
    gestureDom.window.dispatchEvent(
      new gestureDom.window.MessageEvent("message", {
        data: JSON.stringify({ version: 1, type: "sync", sequence, state, ...extra }),
      }),
    );
  /** 同樣的取樣長度才可比：揮手週期約 2.6 秒，窗太短會落在平坦處。 */
  const armPeak = (n) => {
    let peak = 0;
    for (let i = 0; i < n; i += 1) {
      advance(1);
      peak = Math.max(peak, Math.abs(gestureDom.window.kinsunBear.pose.armRShoulder));
    }
    return peak;
  };

  const bear = gestureDom.window.kinsunBear;
  advance(20);

  const greeting = gestureDom.window.PET.behaviorFromEmotion("greeting", 2);
  assert.equal(greeting.hand_gesture, "wave", "打招呼應該推導出揮手");
  assert.equal(
    gestureDom.window.PET.behaviorFromEmotion("calm", 2).hand_gesture,
    "none",
    "平靜不該硬加手勢",
  );

  sync(1, "speaking", { text: "嗨嗨！你來啦！", durationMs: 1000 });
  advance(3);
  assert.equal(bear.behavior?.hand_gesture, "wave", "說話時應已依情緒設好動作意圖");
  let guard = 0;
  while (bear.talking && guard < 400) {
    advance(1);
    guard += 1;
  }
  assert.equal(bear.stateMachine.state, "action", "講完且有手勢時應切到 action");
  assert.ok(armPeak(60) > 10, "揮手應讓右肩明顯抬起（遠大於待機呼吸的幅度）");

  // 對講機講完就送 idle——手勢必須還演得完。
  sync(2, "idle");
  assert.equal(bear.stateMachine.state, "action", "保護期內不可以立刻回待機");
  assert.ok(armPeak(60) > 10, "保護期內手勢應該還在演");

  // ⚠️ 但新狀態一律立即生效：長輩按麥克風時聆聽姿勢不可以慢半拍。
  sync(3, "listening");
  advance(2);
  assert.equal(bear.listening, true, "聆聽必須立即生效，不可被手勢保護擋住");

  // 保護期真的會結束（`setTimeout` 走真實時間，這裡只能等）——否則阿白永遠不回待機。
  sync(4, "speaking", { text: "嗨嗨！你來啦！", durationMs: 200 });
  guard = 0;
  while (bear.talking && guard < 400) {
    advance(1);
    guard += 1;
  }
  sync(5, "idle");
  assert.equal(bear.stateMachine.state, "action", "前提：又進入保護期");
  await new Promise((resolve) => setTimeout(resolve, 1400));
  advance(2);
  assert.equal(bear.stateMachine.state, "idle", "保護期過後必須自己回待機");

  // ── 進畫面打招呼 ──────────────────────────────────────────────────────────
  // ⚠️ 放在最後、`sync` 序號接續往上：這一段用的序號若比前面小，會被單調序號整個
  // 擋掉，而症狀是斷言失敗在**上一段**，很難看出是自己排錯了順序。
  gestureDom.window.dispatchEvent(
    new gestureDom.window.MessageEvent("message", {
      data: JSON.stringify({ version: 1, type: "greet" }),
    }),
  );
  advance(3);
  assert.equal(bear.emotionKey, "greeting", "打招呼應進入 greeting 情緒");
  assert.equal(bear.behavior?.hand_gesture, "wave", "打招呼應推導出揮手");
  assert.ok(armPeak(90) > 10, "打招呼應讓右肩明顯抬起");
  // 走與手勢保護同一顆計時器，所以同樣要驗「被打斷時會讓路」。
  sync(6, "listening");
  advance(3);
  assert.equal(bear.listening, true, "打招呼演到一半按麥克風，聆聽必須立即生效");

  gestureDom.window.close();
}

console.log("Otto renderer 人設、情緒黑名單、手部動作與離線邊界驗證通過。");
