/**
 * 取長輩目前所在的地名與模糊座標。
 *
 * ⚠️ 座標在本檔四捨五入到 0.01 度（約 1.1 公里）之後才上傳，精確值永不離開手機。
 * 隱私邊界劃在資料離開裝置之前——後端一旦收到精確值，它就已經進了伺服器的
 * 記憶體與（潛在的）log，再捨去也來不及。
 *
 * 為什麼要送座標而不是只送地名（PR #55 的原設計）：Open-Meteo 的台灣地名索引只有
 * 6/22 縣市查得到，而本檔回的正是「台南市」這種查不到的字串。而且真正決定天氣的
 * 是海拔不是行政區——實測台北市大安區與市中心完全一樣（32.4°C／毛毛雨），但陽明山
 * 是雷雨、梨山與台中市中心差 8.5°C。只有座標抓得到這件事。
 *
 * 為什麼是 0.01 度：實測出來的交會點。0.1 度（約 11 公里，Open-Meteo 全球網格的
 * 尺度，理論上無損）會把陽明山的雷雨變成毛毛雨；0.01 度與精確座標的天氣幾乎一致。
 *
 * 一切失敗（未授權、無快取位置、譯不出地名）都回 null，由呼叫端當成「這輪沒有
 * 位置」——金孫會照舊開口問，功能靜默降級，絕不阻擋對講機。
 */

import * as Location from "expo-location";

export type ElderPlace = { place: string; latitude: number; longitude: number };

/** 約 1.1 公里見方。市區內是上萬人的範圍，定位不到住址。 */
function blur(value: number): number {
  return Math.round(value * 100) / 100;
}

export async function currentPlace(): Promise<ElderPlace | null> {
  try {
    const { status } = await Location.requestForegroundPermissionsAsync();
    if (status !== Location.PermissionStatus.GRANTED) {
      return null;
    }
    // 用 getLastKnownPositionAsync 而非 getCurrentPositionAsync：官方文件載明後者
    // 可能要等好幾秒，而長輩按下對講機是要馬上講話的。快取位置對城市級精度綽綽有餘。
    const position = await Location.getLastKnownPositionAsync();
    if (position === null) {
      return null;
    }
    const [address] = await Location.reverseGeocodeAsync(position.coords);
    if (!address) {
      return null;
    }
    // 各家作業系統的 city 粒度不一（可能回「台南市」也可能回「東區」）；退階順序
    // 是緩解，不是保證。地名只用於稱呼——查天氣走座標，故粒度不影響準確度。
    const place = address.city ?? address.subregion ?? address.region ?? "";
    if (!place) {
      return null;
    }
    return {
      place,
      latitude: blur(position.coords.latitude),
      longitude: blur(position.coords.longitude),
    };
  } catch {
    return null;
  }
}
