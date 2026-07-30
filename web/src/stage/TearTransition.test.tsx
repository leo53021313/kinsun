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
});
