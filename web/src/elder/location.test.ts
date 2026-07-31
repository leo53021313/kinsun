/**
 * currentPlace 目前一律回 null（見 location.ts 開頭說明：網頁拿不到反查地名
 * API，送半套座標換不到任何後端行為卻已經讓座標離開瀏覽器，故連「成功取得
 * 座標」這條路徑都刻意回 null，不是遺漏）。「一律降級」這種設計若被不小心
 * 改掉（比如有人以為「拿到座標就該送出去」），症狀是長輩每一句話都在瀏覽器
 * 端多打一次定位、卻毫無對話品質改善，且精確座標可能就此離開裝置，沒有
 * 測試永遠抓不到。
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { currentPlace } from "./location";

afterEach(() => vi.unstubAllGlobals());

describe("currentPlace", () => {
  it("瀏覽器沒有定位 API 時回 null", async () => {
    vi.stubGlobal("navigator", {});
    await expect(currentPlace()).resolves.toBeNull();
  });

  it("即使成功取得座標也回 null——網頁沒有反查地名，送半套座標換不到任何後端行為", async () => {
    const getCurrentPosition = vi.fn((success: PositionCallback) => {
      success({ coords: { latitude: 22.99, longitude: 120.21 } } as GeolocationPosition);
    });
    vi.stubGlobal("navigator", { geolocation: { getCurrentPosition } });

    await expect(currentPlace()).resolves.toBeNull();
  });

  it("使用者拒絕定位或逾時，回 null 而非往外拋", async () => {
    const getCurrentPosition = vi.fn(
      (_success: PositionCallback, error: PositionErrorCallback) => {
        error({ code: 1, message: "denied" } as GeolocationPositionError);
      },
    );
    vi.stubGlobal("navigator", { geolocation: { getCurrentPosition } });

    await expect(currentPlace()).resolves.toBeNull();
  });

  it("取位帶入逾時與快取上限選項，不可拖住長輩講話", async () => {
    const getCurrentPosition = vi.fn();
    vi.stubGlobal("navigator", { geolocation: { getCurrentPosition } });

    currentPlace();

    expect(getCurrentPosition.mock.calls[0][2]).toEqual({ timeout: 3000, maximumAge: 300_000 });
  });
});
