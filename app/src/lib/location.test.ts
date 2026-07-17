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

  it("正常時回傳地名與模糊座標", async () => {
    grantPermission();
    mocked.getLastKnownPositionAsync.mockResolvedValue({
      coords: { latitude: 22.9876, longitude: 120.2134 },
    } as never);
    mocked.reverseGeocodeAsync.mockResolvedValue([{ city: "台南市" }] as never);

    expect(await currentPlace()).toEqual({
      place: "台南市",
      latitude: 22.99,
      longitude: 120.21,
    });
  });

  it("座標四捨五入到 0.01 度（約 1.1 公里）", async () => {
    // ⚠️ 四捨五入必須在手機端做：後端一旦收到精確值，它就已經進了伺服器的
    // 記憶體與（潛在的）log。隱私邊界要劃在資料離開裝置之前。
    //
    // 0.01 度是實測出來的交會點：0.1 度（約 11 公里）會把陽明山的雷雨變成
    // 毛毛雨；0.01 度與精確座標的天氣幾乎一致（梨山差 1.3°C，天氣類型相同）。
    grantPermission();
    mocked.getLastKnownPositionAsync.mockResolvedValue({
      coords: { latitude: 25.0261234, longitude: 121.5439876 },
    } as never);
    mocked.reverseGeocodeAsync.mockResolvedValue([{ city: "台北市" }] as never);

    const got = await currentPlace();
    expect(got?.latitude).toBe(25.03);
    expect(got?.longitude).toBe(121.54);
  });

  it("長輩拒絕定位時回空字串（靜默降級，不可阻擋對講機）", async () => {
    mocked.requestForegroundPermissionsAsync.mockResolvedValue({
      status: "denied",
    } as never);

    expect(await currentPlace()).toBeNull();
    expect(mocked.getLastKnownPositionAsync).not.toHaveBeenCalled();
  });

  it("沒有快取位置時回空字串（室內收不到訊號）", async () => {
    grantPermission();
    mocked.getLastKnownPositionAsync.mockResolvedValue(null);

    expect(await currentPlace()).toBeNull();
  });

  it("譯不出地名時回空字串", async () => {
    grantPermission();
    mocked.getLastKnownPositionAsync.mockResolvedValue(POSITION as never);
    mocked.reverseGeocodeAsync.mockResolvedValue([]);

    expect(await currentPlace()).toBeNull();
  });

  it("拋例外時回空字串，不往外拋", async () => {
    mocked.requestForegroundPermissionsAsync.mockRejectedValue(new Error("boom"));

    await expect(currentPlace()).resolves.toBeNull();
  });

  it("city 缺漏時退 subregion", async () => {
    // 各家作業系統的 city 粒度不一，退階順序是緩解（spec 已知限制 4）。
    grantPermission();
    mocked.getLastKnownPositionAsync.mockResolvedValue(POSITION as never);
    mocked.reverseGeocodeAsync.mockResolvedValue([
      { city: null, subregion: "東區", region: "台南市" },
    ] as never);

    expect((await currentPlace())?.place).toBe("東區");
  });

  it("city 與 subregion 皆缺時退 region", async () => {
    grantPermission();
    mocked.getLastKnownPositionAsync.mockResolvedValue(POSITION as never);
    mocked.reverseGeocodeAsync.mockResolvedValue([
      { city: null, subregion: null, region: "台南市" },
    ] as never);

    expect((await currentPlace())?.place).toBe("台南市");
  });
});
