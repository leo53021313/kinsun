/**
 * currentPlace 的四條失敗路徑全是「靜默降級」——錯了不會拋例外、不會有人發現，
 * 只會讓金孫默默失去「問天氣不反問所在地」的能力。這種 bug 沒有測試永遠抓不到。
 */

import * as Location from "expo-location";

import { currentPlace } from "./location";

jest.mock("expo-location", () => ({
  PermissionStatus: { GRANTED: "granted", DENIED: "denied" },
  requestForegroundPermissionsAsync: jest.fn(),
  getLastKnownPositionAsync: jest.fn(),
  reverseGeocodeAsync: jest.fn(),
}));

const mocked = Location as jest.Mocked<typeof Location>;

const POSITION = { coords: { latitude: 22.99, longitude: 120.21 } };

function grantPermission() {
  mocked.requestForegroundPermissionsAsync.mockResolvedValue({
    status: Location.PermissionStatus.GRANTED,
  } as never);
}

describe("currentPlace", () => {
  beforeEach(() => {
    jest.resetAllMocks();
  });

  it("正常時回傳城市名", async () => {
    grantPermission();
    mocked.getLastKnownPositionAsync.mockResolvedValue(POSITION as never);
    mocked.reverseGeocodeAsync.mockResolvedValue([{ city: "台南市" }] as never);

    expect(await currentPlace()).toBe("台南市");
  });

  it("長輩拒絕定位時回空字串（靜默降級，不可阻擋對講機）", async () => {
    mocked.requestForegroundPermissionsAsync.mockResolvedValue({
      status: "denied",
    } as never);

    expect(await currentPlace()).toBe("");
    expect(mocked.getLastKnownPositionAsync).not.toHaveBeenCalled();
  });

  it("沒有快取位置時回空字串（室內收不到訊號）", async () => {
    grantPermission();
    mocked.getLastKnownPositionAsync.mockResolvedValue(null);

    expect(await currentPlace()).toBe("");
  });

  it("譯不出地名時回空字串", async () => {
    grantPermission();
    mocked.getLastKnownPositionAsync.mockResolvedValue(POSITION as never);
    mocked.reverseGeocodeAsync.mockResolvedValue([]);

    expect(await currentPlace()).toBe("");
  });

  it("拋例外時回空字串，不往外拋", async () => {
    mocked.requestForegroundPermissionsAsync.mockRejectedValue(new Error("boom"));

    await expect(currentPlace()).resolves.toBe("");
  });

  it("city 缺漏時退 subregion", async () => {
    // 各家作業系統的 city 粒度不一，退階順序是緩解（spec 已知限制 4）。
    grantPermission();
    mocked.getLastKnownPositionAsync.mockResolvedValue(POSITION as never);
    mocked.reverseGeocodeAsync.mockResolvedValue([
      { city: null, subregion: "東區", region: "台南市" },
    ] as never);

    expect(await currentPlace()).toBe("東區");
  });

  it("city 與 subregion 皆缺時退 region", async () => {
    grantPermission();
    mocked.getLastKnownPositionAsync.mockResolvedValue(POSITION as never);
    mocked.reverseGeocodeAsync.mockResolvedValue([
      { city: null, subregion: null, region: "台南市" },
    ] as never);

    expect(await currentPlace()).toBe("台南市");
  });
});
