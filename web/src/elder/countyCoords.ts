/**
 * 台灣縣市座標反查——把手機定位的精確座標離線換成「台南市」這種縣市級地名。
 *
 * ⚠️ **本檔已備妥、尚未接線（F-17 第二段，見 `docs/dev/12_前端架構規範.md` §9）**：
 * `elder/location.ts::currentPlace` 目前仍是「一律回 `null`、完全不呼叫
 * `navigator.geolocation`」，本檔的 `nearestCounty` 現在**沒有任何呼叫端**。接線
 * 待 `useTalk.ts` 正在進行中的另一輪審查（T4／T6）收尾後才進行，屆時：
 * ①`location.ts` 恢復呼叫 `getCurrentPosition`、用本檔反查地名；
 * ②`useTalk.ts` 新增一條與 `probeMicrophone` 並列的 mount effect，把定位權限
 *   請求移到進畫面時——**不可以放在按住麥克風開錄的當下**（系統權限對話框會
 *   搶走指標，iOS 送 `pointercancel`，錄音被截斷，見 2026-07-18 故障與
 *   `location.ts` 開頭的完整說明）。
 *
 * ## 為什麼要有這張表（而不是打外部地理編碼 API）
 *
 * 瀏覽器沒有 App 端 `expo-location.reverseGeocodeAsync` 那種作業系統級反查
 * 能力，要反查地名得打外部地理編碼 API，而本站 CSP 的 `connect-src 'self'`
 * 只准連自家後端，外部呼叫會被自己擋掉——不能動 CSP、不能加第三方套件、更
 * 不該為此讓後端多一支服務。台灣縣市是**封閉集合**（22 個），地名在管線裡只
 * 用於稱呼（`kinsun.locations.facts` 只需要「台南市」這種字串給金孫說出口），
 * 縣市級精度綽綽有餘，離線查表就能解決，不需要任何網路呼叫。
 *
 * ## 表從哪裡來、如何防止兩份表漂移
 *
 * `COUNTY_COORDS` 逐鍵複製自後端 `src/kinsun/tools/weather.py::_COUNTY_COORDS`
 * （同一批 22 縣市、同一組座標，鍵一律「台」寫法）。Python 與 TypeScript 是兩個
 * 執行環境，這張表沒有辦法共用同一份原始碼——複製之後最怕的是有一天只改了
 * 一邊（例如修正某縣市座標）而沒人發現另一邊沒跟著改，兩份表從此悄悄漂移。
 * `web/scripts/verify-county-coords.mjs` 在每次 `npm run build` 前逐鍵比對本檔
 * 與後端那份**字面值**，兩者不一致就讓建置失敗並印出是哪個縣市、哪個值不合
 * （做法比照 `scripts/verify-wasm-checksum.mjs` 防 wasm 二進位漂移的精神：不
 * 靠人記得，靠建置擋下來）。
 *
 * ⚠️ **這張表若要新增、刪除或修改任何一個縣市，兩邊必須同一個 commit 一起改**，
 * 否則下一次 `npm run build` 會被 `verify-county-coords.mjs` 擋下來。
 */

/** 22 縣市 → 約略座標（縣市政府所在地）。與後端同一份資料，見上方檔頭說明。 */
export const COUNTY_COORDS: Readonly<Record<string, readonly [number, number]>> = {
  "台北市": [25.04, 121.56],
  "新北市": [25.01, 121.46],
  "基隆市": [25.13, 121.74],
  "桃園市": [24.99, 121.30],
  "新竹市": [24.80, 120.97],
  "新竹縣": [24.84, 121.01],
  "苗栗縣": [24.56, 120.82],
  "台中市": [24.14, 120.68],
  "彰化縣": [24.08, 120.54],
  "南投縣": [23.91, 120.66],
  "雲林縣": [23.71, 120.43],
  "嘉義市": [23.48, 120.45],
  "嘉義縣": [23.46, 120.29],
  "台南市": [22.99, 120.21],
  "高雄市": [22.63, 120.30],
  "屏東縣": [22.68, 120.49],
  "宜蘭縣": [24.75, 121.75],
  "花蓮縣": [23.98, 121.60],
  "台東縣": [22.76, 121.14],
  "澎湖縣": [23.57, 119.58],
  "金門縣": [24.44, 118.32],
  "連江縣": [26.16, 119.95],
};

const EARTH_RADIUS_METERS = 6371000;

function toRadians(degrees: number): number {
  return (degrees * Math.PI) / 180;
}

/**
 * 兩點球面距離（公尺）。Haversine 公式，與後端 `places/geo.py::distance_meters`
 * 逐行同一套算法（地球半徑、角度換算完全一致）——純粹是同一件事的 TypeScript 版，
 * 這裡不匯入後端程式碼（不同執行環境），但公式本身沒有理由算出不一樣的答案。
 */
function distanceMeters(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const phi1 = toRadians(lat1);
  const phi2 = toRadians(lat2);
  const dPhi = toRadians(lat2 - lat1);
  const dLambda = toRadians(lon2 - lon1);
  const a =
    Math.sin(dPhi / 2) ** 2 + Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLambda / 2) ** 2;
  return EARTH_RADIUS_METERS * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

/**
 * 座標離最近的縣市代表點超過這個距離（公尺），視為「不在台灣」，`nearestCounty`
 * 回 `null` 而不是硬配一個看起來最近的縣市（V-06）。
 *
 * ⚠️ **寧可保守、也不要硬配**（專案負責人 2026-08-01 裁決）：把一個人在東京的
 * 組員講成「台北市今天…」，比誠實地說不知道更糟——長輩與組員都不會懷疑金孫
 * 講錯，那是比「答不出來」更壞的失敗模式。
 *
 * 120 公里怎麼定出來的：台灣本島狹長的幾個縣（台東縣、花蓮縣、屏東縣）本身
 * 長達七、八十公里，縣內合法座標離「代表點」（縣市政府所在地）天生就可能有
 * 六、七十公里的落差——實測墾丁鵝鑾鼻（21.90, 120.85）離屏東縣代表點約 94.3
 * 公里、蘭嶼（22.66, 121.49）離台東縣代表點約 37.6 公里，兩者都是真實、常見的
 * 台灣座標，不該被判定成「不在台灣」。120 公里留了餘裕收下這類台灣本島與外島
 * 的邊緣案例，同時離最近的國外候選（沖繩那霸約 780 公里、東京約 2100 公里）
 * 還差一個數量級以上，不會把海外座標誤配成台灣的縣市。
 */
const MAX_DISTANCE_METERS = 120_000;

/**
 * 座標 → 最近的台灣縣市名；查不到（座標無效或明顯不在台灣）回 `null`。
 *
 * 純函式、不碰任何瀏覽器 API——呼叫端負責先取得座標（見上方檔頭「尚未接線」
 * 說明）。`latitude`／`longitude` 若不是有限數字（`NaN`／`Infinity`／非數字），
 * 直接回 `null`：這不是「查不到」，是輸入本身不合法，不該假裝算出一個答案。
 *
 * ⚠️ **誠實記載這一道守門目前的份量**：以下方迴圈目前的寫法（`distance <
 * bestDistance` 用 `<` 比較），任何一個非有限值都會讓 `distanceMeters` 算出
 * `NaN`，而 `NaN < Infinity` 恆為 `false`——`bestName` 永遠不會被指派，迴圈跑完
 * 自然留在 `null`，效果與這道守門一樣。單獨拿掉這一行，變異測試不會變紅
 * （已實測確認）。留著是因為它守的是一個**很可能被改動的形狀**：只要有人把這段
 * 比較邏輯換成 `Math.min(...)` 或排序取最小值一類的寫法，`NaN` 的比較語意不一定
 * 還是「恆假」，那時這道守門就是唯一還擋得住非法輸入的地方。
 */
export function nearestCounty(latitude: number, longitude: number): string | null {
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
    return null;
  }
  let bestName: string | null = null;
  let bestDistance = Infinity;
  for (const [name, [countyLat, countyLon]] of Object.entries(COUNTY_COORDS)) {
    const distance = distanceMeters(latitude, longitude, countyLat, countyLon);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestName = name;
    }
  }
  if (bestName === null || bestDistance > MAX_DISTANCE_METERS) {
    return null;
  }
  return bestName;
}
