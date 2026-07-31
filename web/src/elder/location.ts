/**
 * 取長輩目前所在的地名與模糊座標——目前**一律回 `null`，且完全不碰定位 API**。
 *
 * ⚠️ **為什麼連 `getCurrentPosition` 都不呼叫**（全分支審查的 Critical 2）：三條
 * 回呼（成功、失敗、逾時）全部 `resolve(null)` 之後，那通呼叫換到的東西是零，
 * 代價卻是**在錄音進行中跳出一個權限對話框**——`useTalk::startRecording` 是在
 * `recorder.start()` 解出**之後**才發動取位的，那一刻長輩的手指正按在麥克風鍵上。
 * 系統面板搶走指標，iOS Safari 送 `pointercancel`，`TalkScreen` 把它轉成
 * `pressOut`：未達 500ms 門檻時手勢切成點按模式（他以為還按著），已達門檻時直接
 * 送出約 0.3 秒的錄音，後端回一句「沒聽清楚」。而那正是畢典展示的開場那一句。
 *
 * ⚠️ 同一支 `useTalk` 自己在麥克風權限那段寫著「不能等長輩按下去才問——權限對話框
 * 跳出來的當下他的手指正按在鍵上，第一次錄音會被對話框吃掉」（App 在 iOS 上踩過
 * 同一個坑，見 docs/dev/17 的 2026-07-18 故障）。`probeMicrophone` 為此被搬到掛載
 * 時，取位卻在按下去的那一刻引進了第二個權限對話框。
 *
 * ⚠️ **F-17 補上之後要恢復取位**（見下），但**屆時必須把權限請求移到安全的時機**
 * ——例如進畫面時與麥克風權限一起問（`useTalk` 的 `probeMicrophone` effect 旁），
 * **不可以放在開錄的當下**。恢復時原本的取位參數是 `{ timeout: 3000（不可拖住長輩
 * 講話）, maximumAge: 300_000（五分鐘內的快取直接算數，長輩不會五分鐘內走到另一個
 * 縣市）}`，`location.test.ts` 那條「不呼叫」的測試要一併改回。
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

export function currentPlace(): Promise<ElderPlace | null> {
  // ⚠️ 這裡**不呼叫** `navigator.geolocation.getCurrentPosition`：回傳值 100% 會被
  // 丟棄（沒有地名可配，見上），而那通呼叫會在長輩按著麥克風錄音的當下跳出權限
  // 對話框，把他的第一句話吃掉。恢復條件與正確時機見本檔開頭。
  return Promise.resolve(null);
}
