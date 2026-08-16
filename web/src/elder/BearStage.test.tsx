/**
 * 角色舞台與 renderer 的 bridge 接線。
 *
 * jsdom 不會真的執行 iframe 裡的 renderer，所以這裡驗的是**接線本身**：來源驗證、
 * ready 之後補送最後一個狀態、狀態改變時送新指令。renderer 內部的行為（黑名單、
 * 對嘴、SVG 啟動）由 `app/scripts/test-otto-runtime.mjs` 在真的跑起來的 DOM 上驗，
 * 兩邊不重複。
 */

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// ⚠️ 讀的是**這一端真正會載入的那份產物**（`RENDERER_SRC` 指向它），不是
// `shared/otto-pet-core/sentiment.js` 來源：產物與來源一致由 `npm run build` 的
// `build-renderer.mjs --check` 守，這裡再往來源比對只是重複同一件事，而比對產物
// 才涵蓋「來源改了但沒重新產生」這個真實會發生的狀態。
// ⚠️ 用 `?raw` 而不是 `node:fs`：路徑由打包器解析，不依賴測試從哪個目錄啟動
//（jsdom 下 `import.meta.url` 不是 file: scheme，`fileURLToPath` 會擲例外）。
import rendererHtml from "../../public/otto/renderer.html?raw";
import { strings } from "@/strings";

import { BearStage } from "./BearStage";
import { BLOCKED_EMOTIONS, sanitizeEmotion } from "./bearEmotion";

function iframeWindow(): Window {
  const frame = document.querySelector("iframe");
  if (!frame?.contentWindow) throw new Error("找不到 renderer iframe");
  return frame.contentWindow;
}

/** 模擬 renderer 送出 ready；來源刻意可換，用來驗來源檢查。 */
function emitReady(source: Window | null) {
  window.dispatchEvent(
    new MessageEvent("message", {
      data: JSON.stringify({ version: 1, type: "ready" }),
      source: source as MessageEventSource | null,
    }),
  );
}

describe("BearStage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("舞台是純裝飾，狀態交給狀態帶的可見文字說（W3b 起）", () => {
    // W3a 期間這裡掛過 role="img" 與逐狀態的 aria-label，因為當時還沒有狀態帶，
    // 拿掉會讓看不見的長輩失去唯一線索。狀態帶到位後就換過去了——可見文字比
    // aria-label 好，看得見的人與聽的人拿到同一份資訊。狀態帶本身由
    // `TalkScreen.test.tsx` 驗。
    render(<BearStage state="listening" />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByTestId("bear-stage")).toHaveAttribute("aria-hidden", "true");
    // iframe 仍要有 title：即使 aria-hidden，沒有可及名稱的 frame 是 a11y 稽核項。
    expect(document.querySelector("iframe")).toHaveAttribute(
      "title",
      strings.talk.companionTitle,
    );
  });

  it("光暈用該狀態的設計 token，不是寫死的顏色", () => {
    render(<BearStage state="thinking" />);
    const glow = screen.getByTestId("bear-stage-glow");
    expect(glow.style.background).toContain("--talk-thinking-glow");
  });

  it("舞台尺寸是核准的 209 × 300，不隨內容縮放", () => {
    render(<BearStage state="idle" />);
    const stage = screen.getByTestId("bear-stage");
    expect(stage.className).toContain("w-[var(--avatar-stage-w)]");
    expect(stage.className).toContain("h-[var(--avatar-stage-h)]");
  });

  it("收到自己 iframe 的 ready 之後，補送最後一個狀態", () => {
    render(<BearStage state="listening" />);
    const post = vi.spyOn(iframeWindow(), "postMessage");
    emitReady(iframeWindow());
    expect(post).toHaveBeenCalledTimes(1);
    const [payload] = post.mock.calls[0];
    expect(JSON.parse(String(payload))).toMatchObject({
      version: 1,
      type: "sync",
      state: "listening",
    });
  });

  it("不是自己 iframe 送來的 ready 一律不理", () => {
    // 頁面上任何腳本（含瀏覽器擴充）都能對 window 送 message。不驗來源的話，
    // 別人的訊息就能把舞台騙進 ready，而真正的 renderer 還沒起來。
    render(<BearStage state="idle" />);
    const post = vi.spyOn(iframeWindow(), "postMessage");
    emitReady(window);
    emitReady(null);
    expect(post).not.toHaveBeenCalled();
  });

  it("ready 之後狀態改變會送出新指令，且 sequence 遞增", () => {
    const { rerender } = render(<BearStage state="idle" />);
    const post = vi.spyOn(iframeWindow(), "postMessage");
    emitReady(iframeWindow());
    rerender(<BearStage state="speaking" />);

    const commands = post.mock.calls.map((call) => JSON.parse(String(call[0])));
    expect(commands.at(-1)).toMatchObject({ type: "sync", state: "speaking" });
    // renderer 以 sequence 擋重複投遞，倒退或重複會被它整個忽略。
    const sequences = commands.map((command) => command.sequence);
    expect([...sequences]).toEqual([...sequences].sort((a, b) => a - b));
  });

  it("ready 之前不送——iframe 還沒接手，送了也是丟掉", () => {
    const { rerender } = render(<BearStage state="idle" />);
    const post = vi.spyOn(iframeWindow(), "postMessage");
    rerender(<BearStage state="thinking" />);
    expect(post).not.toHaveBeenCalled();
  });

  it("iframe 不給 allow-same-origin：renderer 出事也碰不到頁面的 storage", () => {
    render(<BearStage state="idle" />);
    const frame = document.querySelector("iframe")!;
    expect(frame.getAttribute("sandbox")).toBe("allow-scripts");
  });
});

/** 走完「ready → 換成這組 props」，回傳 renderer 收到的最後一個指令。 */
function lastCommandAfter(props: Parameters<typeof BearStage>[0]) {
  const { rerender } = render(<BearStage state="idle" />);
  const post = vi.spyOn(iframeWindow(), "postMessage");
  emitReady(iframeWindow());
  rerender(<BearStage {...props} />);
  const commands = post.mock.calls.map((call) => JSON.parse(String(call[0])));
  return commands.at(-1);
}

describe("說話對嘴的原料", () => {
  // ⚠️ 這裡驗的是「呈現層有沒有把原料交出去」，不是 renderer 內部怎麼對嘴——後者
  // 由 `app/scripts/test-otto-runtime.mjs` 在真的跑起來的 DOM 上驗，兩邊不重複。
  // 這一層壞掉的症狀是**沒有編譯錯誤、沒有測試紅**，只是阿白說話時嘴不會動。

  it("speaking 時把這一則的字與時長送給 renderer", () => {
    const command = lastCommandAfter({
      state: "speaking",
      speechCue: { key: "t1:reply:1", text: "今天天氣很好", durationMs: 1200 },
    });
    expect(command).toMatchObject({
      state: "speaking",
      text: "今天天氣很好",
      durationMs: 1200,
    });
  });

  it("同一句重播也要送出新指令：key 不同，renderer 才會重新對嘴", () => {
    const { rerender } = render(<BearStage state="idle" />);
    const post = vi.spyOn(iframeWindow(), "postMessage");
    emitReady(iframeWindow());
    const spoken = { text: "該吃藥了喔", durationMs: 900 };
    rerender(<BearStage state="speaking" speechCue={{ key: "t1:reply:1", ...spoken }} />);
    rerender(<BearStage state="speaking" speechCue={{ key: "t1:reply:2", ...spoken }} />);

    const commands = post.mock.calls.map((call) => JSON.parse(String(call[0])));
    const speaking = commands.filter((command) => command.state === "speaking");
    expect(speaking).toHaveLength(2);
    // renderer 以 sequence 擋重複投遞（見 kinsun-bridge.js）：第二次沒有更大的
    // sequence 就會被整個忽略，同一句重播時嘴巴不會再動。
    expect(speaking[1].sequence).toBeGreaterThan(speaking[0].sequence);
  });

  it("非 speaking 態不帶字：協定只在說話時需要對嘴原料", () => {
    const command = lastCommandAfter({
      state: "thinking",
      speechCue: { key: "t1:reply:1", text: "今天天氣很好", durationMs: 1200 },
    });
    expect(command).toMatchObject({ state: "thinking" });
    expect(command).not.toHaveProperty("text");
  });
});

describe("情緒黑名單", () => {
  // ⚠️ CRITICAL（接手指示第 10 條）：阿白可以同理長輩的不舒服，但不能對長輩表現
  // 生氣、不耐、嫌惡、猜忌或驚慌。renderer 內的 `PET.sanitizeEmotion` 是執行期的
  // 真防線；這一層是**送出去之前**就先擋掉，與 App 端 `BearStage.tsx` 同形。

  it("黑名單情緒不會送到 renderer", () => {
    const command = lastCommandAfter({
      state: "speaking",
      emotion: "angry",
      speechCue: { key: "t1:reply:1", text: "你很煩", durationMs: 500 },
    });
    expect(command).toMatchObject({ state: "speaking", text: "你很煩" });
    expect(command).not.toHaveProperty("emotion");
  });

  it("允許的情緒照送——擋的是傷人的那幾種，不是全部", () => {
    const command = lastCommandAfter({
      state: "speaking",
      emotion: "grateful",
      speechCue: { key: "t1:reply:1", text: "謝謝您", durationMs: 500 },
    });
    expect(command).toMatchObject({ emotion: "grateful" });
  });

  it("sanitizeEmotion 對每一個黑名單情緒都回 null", () => {
    for (const emotion of BLOCKED_EMOTIONS) {
      expect(sanitizeEmotion(emotion)).toBeNull();
    }
    expect(sanitizeEmotion("calm")).toBe("calm");
    expect(sanitizeEmotion(null)).toBeNull();
  });

  it("這份黑名單與 renderer 的 BLOCKED_EMOTIONS 是同一份", () => {
    // ⚠️ 兩份清單漂掉**不會有任何症狀**，直到長輩罵阿白的那一刻。App 端由
    // `test-otto-runtime.mjs` 對 `theme.ts` 做同一件事；web 這一份原本沒有任何
    // 閘門守著，那正是「第三份會各自演化的清單」的起點。
    const block = rendererHtml.match(/BLOCKED_EMOTIONS = new Set\(\[([\s\S]*?)\]\)/);
    expect(block, "renderer 產物找不到 BLOCKED_EMOTIONS").not.toBeNull();
    const rendererBlocked = Array.from(block![1].matchAll(/"([a-z]+)"/g)).map((m) => m[1]);
    expect(rendererBlocked.length).toBeGreaterThan(0);
    expect([...BLOCKED_EMOTIONS].sort()).toEqual([...rendererBlocked].sort());
  });
});
