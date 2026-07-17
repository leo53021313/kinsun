/**
 * 取長輩目前所在的地名（如「台南市」）。
 *
 * ⚠️ 經緯度永不離開手機：座標在本檔就譯成地名，只有地名字串會上傳。
 *
 * 一切失敗（未授權、無快取位置、譯不出地名）都回空字串，由呼叫端當成
 * 「這輪沒有位置」——金孫會照舊開口問，功能靜默降級，絕不阻擋對講機。
 */

import * as Location from "expo-location";

export async function currentPlace(): Promise<string> {
  try {
    const { status } = await Location.requestForegroundPermissionsAsync();
    if (status !== Location.PermissionStatus.GRANTED) {
      return "";
    }
    // 用 getLastKnownPositionAsync 而非 getCurrentPositionAsync：官方文件載明後者
    // 可能要等好幾秒，而長輩按下對講機是要馬上講話的。快取位置對城市級精度綽綽有餘
    // ——天氣查的是整個城市，他在哪一區不影響結果。
    const position = await Location.getLastKnownPositionAsync();
    if (position === null) {
      return "";
    }
    const [address] = await Location.reverseGeocodeAsync(position.coords);
    if (!address) {
      return "";
    }
    // 各家作業系統的 city 粒度不一（可能回「台南市」也可能回「東區」）；
    // 退階順序是緩解，不是保證。見 spec 已知限制 4。
    return address.city ?? address.subregion ?? address.region ?? "";
  } catch {
    return "";
  }
}
