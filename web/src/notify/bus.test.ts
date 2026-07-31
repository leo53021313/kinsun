/**
 * 跨欄事件匯流排。
 *
 * ⚠️ 為什麼需要它：輪詢負責「後端主動產生的東西」，但家屬剛按下的那個新增排程，
 * 長輩端要等最多兩秒才看得到——而展示時那兩秒剛好落在「你看，左邊出現了」這句
 * 話的中間。兩欄在同一個 JS 環境裡，直接通知一聲就好。
 */

import { describe, expect, it } from "vitest";
import { act, renderHook } from "@testing-library/react";

import { emitStageEvent, useStageEvent } from "./bus";

describe("跨欄事件", () => {
  it("發出事件後計數會變", () => {
    const { result } = renderHook(() => useStageEvent("guardian-wrote"));
    const before = result.current;
    act(() => emitStageEvent("guardian-wrote"));
    expect(result.current).not.toBe(before);
  });

  it("只收自己訂閱的那個事件", () => {
    const { result } = renderHook(() => useStageEvent("guardian-wrote"));
    const before = result.current;
    act(() => emitStageEvent("elder-talked"));
    expect(result.current).toBe(before);
  });

  it("卸載後不再更新，不會對已卸載的元件 setState", () => {
    const { result, unmount } = renderHook(() => useStageEvent("guardian-wrote"));
    const before = result.current;
    unmount();
    act(() => emitStageEvent("guardian-wrote"));
    expect(result.current).toBe(before);
  });

  it("沒有任何訂閱者時發事件不會爆", () => {
    expect(() => emitStageEvent("elder-talked")).not.toThrow();
  });
});
