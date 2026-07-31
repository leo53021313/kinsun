/**
 * 取長輩目前所在的地名與模糊座標。
 *
 * ⚠️ 網頁沒有反查地名的 API（App 用的是 expo-location 的 reverseGeocodeAsync，
 * 那是作業系統提供的）。後端 `channels/app/turns.py::_save_location` 要求地名
 * 與座標三者同時具備才寫入（缺一律視同「這輪沒有位置」，**不會**寫入空地名
 * ——`locations/store.py::is_valid_place` 對空字串／純空白回 `False`，是早退
 * 而非落庫）。網頁端永遠拿不到地名，若仍把座標送出去，換到的是零功能收益
 * （後端保證整組丟棄），代價卻不是零——座標已經離開瀏覽器，落進伺服器的
 * 記憶體與（潛在的）uvicorn 存取日誌 query string（`logging_setup.py` 刻意
 * 不接管 uvicorn 的 handler）。隱私邊界劃在資料離開裝置之前：這裡選擇**一律
 * 回 `null`、連座標都不送**——與 App 版做法一致（App 拿不到地名時也是整組
 * 不送，見 `lib/location.ts`），零傳輸。
 *
 * 這是已知功能落差（見 docs/dev/12_前端架構規範.md §9 F-17）：要補齊需在
 * 後端加一支座標反查地名的服務、或改讓天氣查詢不要求地名同時存在，兩者皆
 * 超出本模組範圍。
 *
 * 一切情況（未授權、逾時、成功取得座標）皆回 `null`，由呼叫端當成「這輪
 * 沒有位置」——金孫會照舊開口問，功能靜默降級，絕不阻擋對講機。
 */

import type { ElderPlace } from "./api";

/** 取位不可以拖住長輩講話。超過這個時間就當作沒有位置。 */
const TIMEOUT_MS = 3000;

export function currentPlace(): Promise<ElderPlace | null> {
  if (!navigator.geolocation) {
    return Promise.resolve(null);
  }
  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      // 拿到座標也一律回 null：沒有地名可配，送半套換不到任何後端行為，
      // 卻已經讓座標離開瀏覽器——見本檔開頭的隱私與功能落差說明。
      () => resolve(null),
      () => resolve(null),
      { timeout: TIMEOUT_MS, maximumAge: 300_000 },
    );
  });
}
