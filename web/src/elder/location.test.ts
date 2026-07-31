/**
 * currentPlace 目前一律回 null，而且**完全不碰定位 API**（見 location.ts 開頭：
 * 網頁拿不到反查地名 API，送半套座標換不到任何後端行為卻已經讓座標離開瀏覽器，
 * 故連「成功取得座標」這條路徑都刻意回 null，不是遺漏）。
 *
 * ⚠️ **這份測試上一版釘住的是錯的那一邊**：它斷言
 * `getCurrentPosition.mock.calls[0][2]` 等於 `{timeout: 3000, maximumAge: 300_000}`
 * ——也就是**要求那通呼叫必須發生**。那通呼叫的回傳值 100% 被丟棄，代價卻是在長輩
 * 按著麥克風錄音的當下跳出定位權限對話框，把他的第一句話吃掉（全分支審查的
 * Critical 2）。一條有辨別力的測試釘住錯的那一邊，比「恰好通過」更難發現。
 *
 * ⚠️ F-17 補上、恢復取位時要一併改回這裡——但屆時權限請求必須移到進畫面時（與麥克風
 * 權限一起問），不可以放在開錄的當下，見 location.ts 開頭。
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { currentPlace } from "./location";

afterEach(() => vi.unstubAllGlobals());

describe("currentPlace", () => {
  it("瀏覽器沒有定位 API 時回 null", async () => {
    vi.stubGlobal("navigator", {});
    await expect(currentPlace()).resolves.toBeNull();
  });

  it("瀏覽器有定位 API 也回 null——網頁沒有反查地名，送半套座標換不到任何後端行為", async () => {
    const getCurrentPosition = vi.fn((success: PositionCallback) => {
      success({ coords: { latitude: 22.99, longitude: 120.21 } } as GeolocationPosition);
    });
    vi.stubGlobal("navigator", { geolocation: { getCurrentPosition } });

    await expect(currentPlace()).resolves.toBeNull();
  });

  it("不可以去要定位權限——權限對話框會在長輩錄音進行中跳出來，把他的第一句話吃掉", async () => {
    // ⚠️ 這條守的是 Critical 2。`useTalk::startRecording` 是在 `recorder.start()`
    // 解出**之後**才發動取位的，那一刻長輩的手指正按在麥克風鍵上；系統面板搶走
    // 指標，iOS Safari 送 `pointercancel`，那一句話就沒了——與 2026-07-18 App 端
    // 「iPhone 錄音全部 ≤0.72 秒」是同一個坑（見 docs/dev/17）。既然回傳值 100%
    // 被丟棄，就連問都不要問。
    const getCurrentPosition = vi.fn();
    vi.stubGlobal("navigator", { geolocation: { getCurrentPosition } });

    await expect(currentPlace()).resolves.toBeNull();

    expect(getCurrentPosition).not.toHaveBeenCalled();
  });
});
