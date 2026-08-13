/** 光暈綻放動畫。
 *
 * 動畫本身沒辦法用 jsdom 驗（沒有版面與合成器），所以測的是**它的契約**：
 * 該不該播、播完有沒有通知、以及「使用者關了動態效果時要走短路」。
 * 最後一條是無障礙要求（W-11），漏掉的話會讓對動態敏感的人不舒服。
 */

import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BLOOM_DURATION_MS, BloomTransition, REDUCED_MOTION_MS } from "./BloomTransition";

function mockReducedMotion(reduced: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: reduced && query.includes("prefers-reduced-motion"),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("BloomTransition", () => {
  it("未啟動時原樣顯示內容，不掛 overlay", () => {
    mockReducedMotion(false);
    render(
      <BloomTransition active={false} onDone={vi.fn()}>
        <p>開場</p>
      </BloomTransition>,
    );
    expect(screen.getByText("開場")).toBeInTheDocument();
    expect(screen.queryByTestId("bloom-glow")).not.toBeInTheDocument();
  });

  it("啟動時掛上開場頁副本與光暈", () => {
    mockReducedMotion(false);
    render(
      <BloomTransition active onDone={vi.fn()}>
        <p>開場</p>
      </BloomTransition>,
    );
    expect(screen.getByTestId("bloom-page")).toBeInTheDocument();
    expect(screen.getByTestId("bloom-glow")).toBeInTheDocument();
  });

  it("動畫播完後通知呼叫端", () => {
    vi.useFakeTimers();
    mockReducedMotion(false);
    const onDone = vi.fn();
    render(
      <BloomTransition active onDone={onDone}>
        <p>開場</p>
      </BloomTransition>,
    );
    expect(onDone).not.toHaveBeenCalled();
    vi.advanceTimersByTime(BLOOM_DURATION_MS);
    expect(onDone).toHaveBeenCalledOnce();
  });

  it("使用者關了動態效果時改走短的淡出", () => {
    vi.useFakeTimers();
    mockReducedMotion(true);
    const onDone = vi.fn();
    render(
      <BloomTransition active onDone={onDone}>
        <p>開場</p>
      </BloomTransition>,
    );
    vi.advanceTimersByTime(REDUCED_MOTION_MS);
    expect(onDone).toHaveBeenCalledOnce();
  });

  it("關了動態效果時不掛光暈，只淡出", () => {
    mockReducedMotion(true);
    render(
      <BloomTransition active onDone={vi.fn()}>
        <p>開場</p>
      </BloomTransition>,
    );
    expect(screen.queryByTestId("bloom-glow")).not.toBeInTheDocument();
    expect(screen.getByText("開場")).toBeInTheDocument();
  });

  it("父層在動畫期間重繪也不會重排計時器", () => {
    // ⚠️ 這正是最可能發生的情境：舞台在動畫期間掛載並發請求，資料回來就是一次重繪。
    // onDone 若留在相依陣列，計時器會被反覆重排，動畫播完卻沒有人被通知。
    vi.useFakeTimers();
    mockReducedMotion(false);
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = render(
      <BloomTransition active onDone={first}>
        <p>開場</p>
      </BloomTransition>,
    );
    vi.advanceTimersByTime(BLOOM_DURATION_MS - 100);
    rerender(
      <BloomTransition active onDone={second}>
        <p>開場</p>
      </BloomTransition>,
    );
    vi.advanceTimersByTime(100);
    expect(second).toHaveBeenCalledOnce();
    expect(first).not.toHaveBeenCalled();
  });

  it("overlay 對讀螢幕的人隱藏", () => {
    // 開場頁的內容在 DOM 裡出現兩次（後方舞台旁邊多一份動畫用的副本），那份是
    // 裝飾。不隱藏的話會被唸兩遍。
    mockReducedMotion(false);
    const { container } = render(
      <BloomTransition active onDone={vi.fn()}>
        <p>開場</p>
      </BloomTransition>,
    );
    const overlay = container.querySelector("[aria-hidden]");
    expect(overlay).not.toBeNull();
    expect(overlay?.querySelector("[data-testid='bloom-glow']")).not.toBeNull();
  });

  it("給了 origin 時光暈以那個點為圓心", () => {
    mockReducedMotion(false);
    render(
      <BloomTransition active onDone={vi.fn()} origin={{ x: 120, y: 340 }}>
        <p>開場</p>
      </BloomTransition>,
    );
    expect(screen.getByTestId("bloom-glow")).toHaveStyle({ left: "120px", top: "340px" });
  });

  it("沒給 origin 時光暈退回畫面正中央", () => {
    // ⚠️ 呼叫端不一定給得出座標（例如未來從別處觸發轉場），元件不該假設它一定在。
    mockReducedMotion(false);
    render(
      <BloomTransition active onDone={vi.fn()}>
        <p>開場</p>
      </BloomTransition>,
    );
    expect(screen.getByTestId("bloom-glow")).toHaveStyle({ left: "50%", top: "50%" });
  });
});
