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

import { strings } from "@/strings";

import { BearStage } from "./BearStage";

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

  it("狀態以 aria-label 說出來——看不見的長輩只有這條線索", () => {
    // ⚠️ App 那側的舞台是純裝飾，因為狀態由狀態帶的文字說出來；網頁版的狀態帶要
    // 到 W3b 才有。在那之前拿掉 aria-label，視障長輩會完全不知道阿白在做什麼。
    render(<BearStage state="listening" />);
    expect(screen.getByRole("img", { name: strings.talk.avatar.listening })).toBeInTheDocument();
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
