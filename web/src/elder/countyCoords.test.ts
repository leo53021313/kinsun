/**
 * `countyCoords.ts` 的單元測試——純函式，不碰瀏覽器 API（見該檔檔頭「尚未接線」
 * 說明）。距離皆用 Haversine 實測算出，寫進註解的公里數與 `nearestCounty.ts`
 * 檔頭引用的實測值一致，避免「猜一個數字寫進註解」。
 */

import { describe, expect, it } from "vitest";

import { COUNTY_COORDS, nearestCounty } from "./countyCoords";

describe("nearestCounty", () => {
  it("台北 101 附近的座標查得到台北市（約 0.9 公里）", () => {
    expect(nearestCounty(25.033, 121.5654)).toBe("台北市");
  });

  it("高雄車站附近的座標查得到高雄市（約 0.8 公里）", () => {
    expect(nearestCounty(22.6373, 120.3024)).toBe("高雄市");
  });

  it("花蓮市區的座標查得到花蓮縣（約 0.7 公里）", () => {
    expect(nearestCounty(23.9739, 121.6015)).toBe("花蓮縣");
  });

  it("金門本島的座標查得到金門縣（外島、與本島縣市距離遙遠仍要對）", () => {
    expect(nearestCounty(24.4321, 118.3175)).toBe("金門縣");
  });

  it("邊緣案例：墾丁鵝鑾鼻離屏東縣代表點約 94.3 公里，仍在門檻內、判給屏東縣", () => {
    // ⚠️ 這是真實會發生的台灣座標（本島最南端），不是隨手編的數字——縣市代表點
    // 是「縣市政府所在地」，狹長縣份的邊緣本來就會離代表點有數十公里。
    expect(nearestCounty(21.9019, 120.8511)).toBe("屏東縣");
  });

  it("邊緣案例：蘭嶼離台東縣代表點約 37.6 公里，明確判給台東縣", () => {
    expect(nearestCounty(22.6621, 121.4907)).toBe("台東縣");
  });

  it("明顯在國外（東京）時回 null，不硬配一個看起來最近的縣市", () => {
    // 距離最近的表列縣市（宜蘭縣）約 2100 公里，遠遠超過 120 公里門檻。
    expect(nearestCounty(35.6762, 139.6503)).toBeNull();
  });

  it("明顯在國外（沖繩那霸）時回 null——比東京近，仍要擋下來", () => {
    // 距離最近的表列縣市（連江縣）約 771 公里，仍遠超門檻，用來確認門檻不是
    // 隨便設一個「東京距離的一半」就過關的數字。
    expect(nearestCounty(26.2124, 127.6809)).toBeNull();
  });

  it("座標不是有限數字時回 null（NaN／Infinity），不是「查不到」而是輸入不合法", () => {
    expect(nearestCounty(Number.NaN, 121.5)).toBeNull();
    expect(nearestCounty(25, Number.POSITIVE_INFINITY)).toBeNull();
  });

  it("表裡剛好是 22 個台灣縣市，數量不能悄悄變動", () => {
    expect(Object.keys(COUNTY_COORDS)).toHaveLength(22);
  });
});
