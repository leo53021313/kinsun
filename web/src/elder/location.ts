/**
 * 取長輩目前所在的地名與模糊座標。
 *
 * ⚠️ 座標在本檔四捨五入到 0.01 度（約 1.1 公里）之後才上傳，精確值永不離開瀏覽器。
 * 隱私邊界劃在資料離開裝置之前——後端一旦收到精確值，它就已經進了伺服器的記憶體
 * 與（潛在的）log，再捨去也來不及。這與 App 版的 `lib/location.ts` 同一條規則。
 *
 * ⚠️ 網頁沒有反查地名的 API（App 用的是 expo-location 的 reverseGeocodeAsync，
 * 那是作業系統提供的）。這裡只送座標、地名留空——後端的天氣查詢本來就是靠座標，
 * 地名只用於稱呼。**送空地名時整組不送**（後端要求三者同時具備，見 `turns.py`
 * 的 `_save_location`），故網頁端這一輪視同沒有位置。
 *
 * 一切失敗（未授權、逾時）都回 null，由呼叫端當成「這輪沒有位置」——金孫會照舊
 * 開口問，功能靜默降級，絕不阻擋對講機。
 */

import type { ElderPlace } from "./api";

/** 約 1.1 公里見方。市區內是上萬人的範圍，定位不到住址。 */
function blur(value: number): number {
  return Math.round(value * 100) / 100;
}

/** 取位不可以拖住長輩講話。超過這個時間就當作沒有位置。 */
const TIMEOUT_MS = 3000;

export function currentPlace(): Promise<ElderPlace | null> {
  if (!navigator.geolocation) {
    return Promise.resolve(null);
  }
  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (position) =>
        resolve({
          // 地名留空：網頁端沒有作業系統級的反查。後端會因此視為「這輪沒有位置」
          // ——這是刻意接受的降級，見本檔開頭的說明。
          place: "",
          latitude: blur(position.coords.latitude),
          longitude: blur(position.coords.longitude),
        }),
      () => resolve(null),
      { timeout: TIMEOUT_MS, maximumAge: 300_000 },
    );
  });
}
