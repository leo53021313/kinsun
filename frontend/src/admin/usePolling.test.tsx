/**
 * usePolling：訊息流每 5 秒輪詢的核心。PR #56 動過它的 ref 更新時機，
 * 而它當時沒有任何測試守著——本檔補上。
 */

import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { usePolling } from "./usePolling";

function setHidden(hidden: boolean) {
  Object.defineProperty(document, "hidden", { value: hidden, configurable: true });
  document.dispatchEvent(new Event("visibilitychange"));
}

describe("usePolling", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    setHidden(false);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("掛載時立刻跑一次", () => {
    const callback = vi.fn();

    renderHook(() => usePolling(callback, 5000));

    expect(callback).toHaveBeenCalledTimes(1);
  });

  it("依間隔重複執行", () => {
    const callback = vi.fn();
    renderHook(() => usePolling(callback, 5000));

    act(() => void vi.advanceTimersByTime(15_000));

    expect(callback).toHaveBeenCalledTimes(4); // 掛載 1 次 ＋ 三次 tick
  });

  it("分頁隱藏時暫停、回到前景立刻補跑一次", () => {
    const callback = vi.fn();
    renderHook(() => usePolling(callback, 5000));
    callback.mockClear();

    act(() => setHidden(true));
    act(() => void vi.advanceTimersByTime(15_000));
    expect(callback).not.toHaveBeenCalled();

    act(() => setHidden(false));
    expect(callback).toHaveBeenCalledTimes(1);
  });

  it("卸載後不再執行", () => {
    const callback = vi.fn();
    const { unmount } = renderHook(() => usePolling(callback, 5000));
    callback.mockClear();

    unmount();
    act(() => void vi.advanceTimersByTime(15_000));

    expect(callback).not.toHaveBeenCalled();
  });

  it("callback 換新後，下一次 tick 用新的", () => {
    // ⚠️ 這條釘住的是「行為」而非「實作」：PR #56 之前的寫法（render 期間指派
    // ref）在功能上也能通過本測試——它壞的是並發渲染下的正確性，fake timer 測
    // 不出來。但若那個 ref 更新被整個刪掉，輪詢會永遠呼叫第一次的 callback
    // （拿著過期的閉包）而畫面看起來完全正常，這條就抓得到。
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = renderHook(({ cb }) => usePolling(cb, 5000), {
      initialProps: { cb: first },
    });

    rerender({ cb: second });
    first.mockClear();
    second.mockClear();

    act(() => void vi.advanceTimersByTime(5000));

    expect(second).toHaveBeenCalledTimes(1);
    expect(first).not.toHaveBeenCalled();
  });

  it("callback 換新不會重啟計時器", () => {
    // 計時器只相依 intervalMs——這正是本 hook 用 ref 保存 callback 的初衷。
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = renderHook(({ cb }) => usePolling(cb, 5000), {
      initialProps: { cb: first },
    });

    act(() => void vi.advanceTimersByTime(3000)); // 距下次 tick 剩 2 秒
    rerender({ cb: second });
    second.mockClear();

    act(() => void vi.advanceTimersByTime(2000)); // 若重啟，這裡不會 tick

    expect(second).toHaveBeenCalledTimes(1);
  });
});
