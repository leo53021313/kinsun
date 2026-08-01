/** 撕裂展開動畫。
 *
 * 動畫本身沒辦法用 jsdom 驗（沒有版面與合成器），所以測的是**它的契約**：
 * 該不該播、播完有沒有通知、以及「使用者關了動態效果時要走短路」。
 * 最後一條是無障礙要求（W-11），漏掉的話會讓對動態敏感的人不舒服。
 */

import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { REDUCED_MOTION_MS, TEAR_DURATION_MS, TearTransition } from "./TearTransition";

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

describe("TearTransition", () => {
  it("未啟動時原樣顯示內容，不套任何動畫類名", () => {
    mockReducedMotion(false);
    render(
      <TearTransition active={false} onDone={vi.fn()}>
        <p>開場</p>
      </TearTransition>,
    );
    expect(screen.getByText("開場")).toBeInTheDocument();
    expect(screen.queryByTestId("tear-left")).not.toBeInTheDocument();
  });

  it("啟動時把內容切成左右兩半", () => {
    mockReducedMotion(false);
    render(
      <TearTransition active onDone={vi.fn()}>
        <p>開場</p>
      </TearTransition>,
    );
    expect(screen.getByTestId("tear-left")).toBeInTheDocument();
    expect(screen.getByTestId("tear-right")).toBeInTheDocument();
  });

  it("動畫播完後通知呼叫端", () => {
    vi.useFakeTimers();
    mockReducedMotion(false);
    const onDone = vi.fn();
    render(
      <TearTransition active onDone={onDone}>
        <p>開場</p>
      </TearTransition>,
    );
    expect(onDone).not.toHaveBeenCalled();
    vi.advanceTimersByTime(TEAR_DURATION_MS);
    expect(onDone).toHaveBeenCalledOnce();
  });

  it("使用者關了動態效果時改走短的淡出", () => {
    vi.useFakeTimers();
    mockReducedMotion(true);
    const onDone = vi.fn();
    render(
      <TearTransition active onDone={onDone}>
        <p>開場</p>
      </TearTransition>,
    );
    vi.advanceTimersByTime(REDUCED_MOTION_MS);
    expect(onDone).toHaveBeenCalledOnce();
  });

  it("關了動態效果時不做撕裂，只淡出", () => {
    mockReducedMotion(true);
    render(
      <TearTransition active onDone={vi.fn()}>
        <p>開場</p>
      </TearTransition>,
    );
    expect(screen.queryByTestId("tear-left")).not.toBeInTheDocument();
  });

  it("父層在動畫期間重繪也不會重排計時器", () => {
    // ⚠️ 這正是最可能發生的情境：舞台在動畫期間掛載並發請求，資料回來就是一次重繪。
    // onDone 若留在相依陣列，計時器會被反覆重排，動畫播完卻沒有人被通知。
    vi.useFakeTimers();
    mockReducedMotion(false);
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = render(
      <TearTransition active onDone={first}>
        <p>開場</p>
      </TearTransition>,
    );
    vi.advanceTimersByTime(TEAR_DURATION_MS - 100);
    rerender(
      <TearTransition active onDone={second}>
        <p>開場</p>
      </TearTransition>,
    );
    vi.advanceTimersByTime(100);
    expect(second).toHaveBeenCalledOnce();
    expect(first).not.toHaveBeenCalled();
  });

  it("撕開的兩層對讀螢幕的人隱藏", () => {
    // 同一份內容在 DOM 裡有兩份（那是撕裂效果的做法），但它們是裝飾——動畫期間
    // 真正的內容是後方已經掛載的舞台。不隱藏的話會被唸兩遍。
    mockReducedMotion(false);
    const { container } = render(
      <TearTransition active onDone={vi.fn()}>
        <p>開場</p>
      </TearTransition>,
    );
    const overlay = container.querySelector("[aria-hidden]");
    expect(overlay).not.toBeNull();
    expect(overlay?.querySelectorAll("[data-testid^='tear-']")).toHaveLength(2);
  });
});
