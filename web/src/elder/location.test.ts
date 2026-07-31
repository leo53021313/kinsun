/**
 * currentPlace 的三條路徑（無 API、成功、失敗）皆為「靜默降級」——錯了不會拋
 * 例外、不會有人發現，只會讓金孫默默失去「問天氣不反問所在地」的能力。
 * 這種 bug 沒有測試永遠抓不到（同 App 版 `lib/location.test.ts` 的理由）。
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { currentPlace } from "./location";

afterEach(() => vi.unstubAllGlobals());

describe("currentPlace", () => {
  it("瀏覽器沒有定位 API 時回 null", async () => {
    vi.stubGlobal("navigator", {});
    await expect(currentPlace()).resolves.toBeNull();
  });

  it("定位成功時回傳模糊座標，地名一律空字串（網頁端沒有反查地名的 API）", async () => {
    const getCurrentPosition = vi.fn((success: PositionCallback) => {
      success({ coords: { latitude: 22.9876, longitude: 120.2134 } } as GeolocationPosition);
    });
    vi.stubGlobal("navigator", { geolocation: { getCurrentPosition } });

    await expect(currentPlace()).resolves.toEqual({
      place: "",
      latitude: 22.99,
      longitude: 120.21,
    });
  });

  it("座標四捨五入到 0.01 度（約 1.1 公里），精確值不外流", async () => {
    const getCurrentPosition = vi.fn((success: PositionCallback) => {
      success({ coords: { latitude: 25.0261234, longitude: 121.5439876 } } as GeolocationPosition);
    });
    vi.stubGlobal("navigator", { geolocation: { getCurrentPosition } });

    const got = await currentPlace();
    expect(got?.latitude).toBe(25.03);
    expect(got?.longitude).toBe(121.54);
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
