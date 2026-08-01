/**
 * 取長輩目前所在的地名與模糊座標——**F-17 第二段：已恢復取位**（2026-08-01，
 * 承接第一段 `countyCoords.ts` 落地的縣市反查；T4／T6 收尾後由專案負責人核准
 * 動工）。
 *
 * ## 這裡在做什麼、為什麼現在可以恢復呼叫 `getCurrentPosition`
 *
 * 網頁沒有反查地名的 API（App 用的是 `expo-location` 的 `reverseGeocodeAsync`，
 * 那是作業系統提供的），過去因此**完全不呼叫** `navigator.geolocation`——回傳值
 * 100% 會被丟棄（沒有地名可配），代價卻是在長輩按住麥克風錄音的當下跳出定位
 * 權限對話框，把他的第一句話吃掉（全分支審查 Critical 2）。
 *
 * 現在有了 `countyCoords.ts` 的離線縣市反查，座標可以換成「台南市」這種縣市級
 * 地名，半套換不到後端行為的問題已解決；**但權限對話框跳出的時機仍然不能變**
 * ——本檔自己不知道、也不該假設「現在是不是安全的時機」，這件事由呼叫端負責：
 * `elder/useTalk.ts` 新增了一條與 `probeMicrophone` 並列的 mount effect，進畫面
 * 就呼叫一次本函式暖權限（見該檔），錄音時 `startRecording()` 那行呼叫則保留
 * 不動——同一 origin 的定位權限只會跳一次對話框，之後的呼叫直接使用瀏覽器自己
 * 的位置快取（`maximumAge`），不會在錄音進行中再跳窗。
 *
 * ## 座標怎麼處理：反查地名不等於降級座標精度
 *
 * `nearestCounty` 只用來產生「稱呼用」的地名字串；**送給後端的座標仍是手機回報
 * 的實際座標**（模糊化後），不是縣市代表點的座標。理由與 App 版 `lib/location.ts`
 * 完全一致：真正決定天氣的是海拔不是行政區（實測台北市大安區與陽明山天氣天差
 * 地遠），附近地點搜尋更是需要真實座標才查得到「附近」——降級成縣市代表點的話，
 * 「附近有什麼藥局」會變成查縣市政府旁邊有什麼藥局，那不是長輩問的東西。
 *
 * 座標四捨五入到 0.01 度（約 1.1 公里）才離開瀏覽器，精確值永不上傳——與 App 版
 * `blur()` 同一個理由：隱私邊界劃在資料離開裝置之前，後端一旦收到精確值，它就
 * 已經進了伺服器的記憶體與（潛在的）log，再捨去也來不及。
 *
 * ## 反查不到（人在海外）時：整組不送，不是送半套
 *
 * `nearestCounty` 對明顯不在台灣的座標回 `null`（見該檔門檻說明）。這裡選擇
 * **整組回 `null`、連座標都不送**——理由與過去「半套換不到後端行為就不送」的
 * 判斷同一個形狀：`locations/store.py::is_valid_place` 對空字串回 `False`，送
 * 一個空地名換不到 `_save_location` 寫入，等於白白讓座標離開瀏覽器卻沒有任何
 * 功能收益；不確定地名時乾脆不送，也是隱私邊界上更保守的選擇。
 *
 * ## 失敗路徑
 *
 * 瀏覽器不支援定位 API、權限被拒、逾時（3 秒）、座標明顯不在台灣，四種情況皆
 * 回 `null`，由呼叫端當成「這輪沒有位置」——金孫會照舊開口問，功能靜默降級，
 * 絕不阻擋對講機。
 *
 * 這是 `docs/dev/12_前端架構規範.md` §9 F-17 的第二段修復；天氣、附近地點、
 * 交通路線三者受影響的程度不同，見該文件段落。
 */

import type { ElderPlace } from "./api";
import { nearestCounty } from "./countyCoords";

/**
 * `timeout`：不可拖住長輩講話，3 秒內拿不到就放棄（`startRecording()` 是不等待
 * 這個 Promise 的，但 `stopAndSend()` 送出時會等，故仍要有上限）。
 * `maximumAge`：5 分鐘內的快取位置直接算數，長輩不會在 5 分鐘內走到另一個縣市，
 * 也讓 mount 時暖過權限之後、`startRecording()` 再次呼叫幾乎瞬時解出。
 */
const GEOLOCATION_OPTIONS: PositionOptions = { timeout: 3000, maximumAge: 300_000 };

/** 約 1.1 公里見方。市區內是上萬人的範圍，定位不到住址（同 App 版 `blur()`）。 */
function blur(value: number): number {
  return Math.round(value * 100) / 100;
}

export function currentPlace(): Promise<ElderPlace | null> {
  return new Promise((resolve) => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      resolve(null);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const place = nearestCounty(position.coords.latitude, position.coords.longitude);
        // 反查不到（明顯不在台灣、或座標本身不合法）：整組不送，見檔頭說明。
        if (place === null) {
          resolve(null);
          return;
        }
        resolve({
          place,
          latitude: blur(position.coords.latitude),
          longitude: blur(position.coords.longitude),
        });
      },
      () => resolve(null),
      GEOLOCATION_OPTIONS,
    );
  });
}
