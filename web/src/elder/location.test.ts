/**
 * `currentPlace` F-17 第二段：已恢復取位（見 `location.ts` 檔頭）。
 *
 * ⚠️ **這份測試上一版釘住的是「不可以呼叫 `getCurrentPosition`」**——那在當時是
 * 對的：半套換不到後端行為，呼叫只會在錄音進行中跳出權限對話框。現在有
 * `countyCoords.ts` 的離線縣市反查，半套的問題已解決，而**權限對話框的安全時機
 * 改由呼叫端（`useTalk.ts` 新增的 mount effect）負責**——本檔不再是那道守門的
 * 承載處，故這裡改回驗證 `getCurrentPosition` 真的會被呼叫、且帶著正確的選項。
 * 「不可以在開錄當下要權限」這件事現在測在 `useTalk.test.ts`。
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { currentPlace } from "./location";

afterEach(() => vi.unstubAllGlobals());

/** 造一個會呼叫成功回呼、回報指定座標的假 `navigator.geolocation`。 */
function stubGeolocationSuccess(latitude: number, longitude: number) {
  const getCurrentPosition = vi.fn((success: PositionCallback) => {
    success({ coords: { latitude, longitude } } as GeolocationPosition);
  });
  vi.stubGlobal("navigator", { geolocation: { getCurrentPosition } });
  return getCurrentPosition;
}

describe("currentPlace", () => {
  it("瀏覽器沒有定位 API 時回 null", async () => {
    vi.stubGlobal("navigator", {});
    await expect(currentPlace()).resolves.toBeNull();
  });

  it("台灣座標（台南市）成功取得時，回傳反查出的縣市名與模糊化座標", async () => {
    stubGeolocationSuccess(22.9908123, 120.2133456);
    await expect(currentPlace()).resolves.toEqual({
      place: "台南市",
      latitude: 22.99,
      longitude: 120.21,
    });
  });

  it("明顯不在台灣的座標（東京）：整組回 null，不送半套座標", async () => {
    // 反查不到縣市時，座標本身也不該離開瀏覽器——見 location.ts 檔頭「反查不到
    // 時整組不送」的說明。用 spy 確認座標真的沒有被讀出來包進回傳值。
    const getCurrentPosition = stubGeolocationSuccess(35.6762, 139.6503);
    await expect(currentPlace()).resolves.toBeNull();
    expect(getCurrentPosition).toHaveBeenCalled();
  });

  it("座標帶著正確的選項呼叫 getCurrentPosition（3 秒逾時＋5 分鐘快取）", async () => {
    const getCurrentPosition = stubGeolocationSuccess(22.99, 120.21);
    await currentPlace();
    expect(getCurrentPosition).toHaveBeenCalledWith(
      expect.any(Function),
      expect.any(Function),
      { timeout: 3000, maximumAge: 300_000 },
    );
  });

  it("權限被拒／逾時（失敗回呼）時回 null", async () => {
    const getCurrentPosition = vi.fn(
      (_success: PositionCallback, error: PositionErrorCallback) => {
        error({ code: 1, message: "denied" } as GeolocationPositionError);
      },
    );
    vi.stubGlobal("navigator", { geolocation: { getCurrentPosition } });

    await expect(currentPlace()).resolves.toBeNull();
  });

  it("座標會模糊化到 0.01 度（約 1.1 公里），精確值不外流", async () => {
    stubGeolocationSuccess(22.987654, 120.214321);
    const result = await currentPlace();
    expect(result).toEqual({ place: "台南市", latitude: 22.99, longitude: 120.21 });
  });
});
