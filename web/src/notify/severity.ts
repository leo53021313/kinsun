/**
 * 後端 `severity` → 橫幅樣式的收斂（2026-08-01）。
 *
 * ⚠️ **為什麼需要這一層，而不是直接用後端送來的字串**：這個欄位有三種讀得到
 * 「不是 `notice` 也不是 `alert`」的情形，而三種在畫面上都不可以炸：
 * 1. **欄位不存在**：後端還沒部署到 2026-08-01 之後的版本，或使用者正在讀
 *    加欄之前寫入的舊通知（那些列一律是 `notice`，見 `src/kinsun/db.py`）。
 * 2. **值認不得**：後端日後新增了第三個值，而使用者的分頁還是舊版前端（web 是
 *    純前端 SPA，瀏覽器會快取；後端先上、前端後上是常態）。
 * 3. **型別說謊**：`AppNotification.severity` 的型別是編譯期的宣告，執行期
 *    真正跑的是 `fetch` 回來的任意 JSON，TypeScript 一個字都保證不了。
 *
 * ⚠️ **未知值一律降級成 `notice`，而不是升級成 `alert`**——這個方向是刻意選的，
 * 而且**有代價**，寫在這裡讓下一個人自己判斷要不要改：
 * - 選 `notice` 的理由：未知值最可能來自「後端新增了一個較不緊急的種類」
 *   （如系統公告、帳號事件）。若未知一律變紅，那種通知一上線，畫面上會突然
 *   冒出一片紅色警報，而「警報染多了就沒人看」正是 2026-07-26 全流程實測報告
 *   記下的「狼來了」效應——那會反過來弄壞這整個功能想達成的事。
 * - **代價**：如果後端新增的是比 `alert` 更嚴重的等級（如 `emergency`），這一版
 *   前端會把它靜靜地畫成一般通知。**所以後端新增任何 severity 值時，必須同一
 *   時間更新本檔的 `ALERT_SEVERITIES`**；`src/kinsun/notifications/models.py`
 *   的檔頭已經寫下同一條約束，兩邊互指。
 *
 * ⚠️ **不要改成用 `content` 字串比對關鍵字（「跌倒」「危急」）來補救**：那是臆測
 * 而非真實訊號，會讓「什麼算危急」的判斷散落在前端字串比對裡，而不是後端
 * `safety/` 模組已有的權威分級結果。加這個欄位的全部意義就是為了不必那樣做。
 */

import type { NotificationSeverity } from "kinsun-shared/types";

/** 該畫成紅色警報＋打斷式宣告的值。後端新增更嚴重的等級時，這裡要一起加。 */
const ALERT_SEVERITIES: readonly string[] = ["alert"];

/** 這一版前端認得的全部值。認得的不留痕，認不得的才留痕（見下）。 */
const KNOWN_SEVERITIES: readonly string[] = ["notice", "alert"];

/** 橫幅實際畫得出來的兩種樣式。 */
export type BannerSeverity = "notice" | "alert";

/**
 * 「這個值我不認得」的三種合法表示法：欄位不存在（後端未部署到 2026-08-01 之後
 * 的版本）、JSON `null`、空字串。這三種**不留痕**——它們是可預期的常態（舊資料
 * 一律如此），留痕只會製造沒有人會讀的雜訊，反而蓋掉下面那種真的該看的。
 */
function isAbsent(raw: unknown): boolean {
  return raw === undefined || raw === null || raw === "";
}

/**
 * 把後端送來的任意值收斂成橫幅畫得出來的兩種之一。
 *
 * 刻意收 `unknown`（不是 `NotificationSeverity | undefined`）：呼叫端拿到的是
 * `fetch` 回來的 JSON，型別宣告在執行期不成立，收窄的參數型別只會逼呼叫端寫
 * 一個把問題藏起來的斷言。
 *
 * ⚠️ **認不得的值會留痕（T3 審查 Important 2，2026-08-01 補）**：先前這裡是純
 * 三元式、一個字都不寫。**降級本身是對的，靜默降級不是**——上面那段「代價」寫得
 * 很清楚：後端新增 `emergency`（比 alert 更嚴重）、後端先部署（常態）、使用者
 * 瀏覽器仍快取舊 SPA，於是每一則 `emergency` 都被畫成白色禮貌橫幅，而
 * `logs/` 沒有一行、Opik 沒有一個 span、console 沒有一個字，**只能靠有人現場
 * 肉眼發現**。而唯一的防護是「兩邊檔頭互指、新增值時記得同步更新」這種人為
 * 紀律——這個專案歷史上失敗過兩次的正是那一種。
 *
 * 只對「有值但認不得」warn，不對 `isAbsent` 那三種 warn：後者是可預期的常態。
 * 呼叫端是 `useNotificationFeed` 的 `fresh.map(...)`，**每則新通知只會過一次**
 * （`pickNewItems` 只回比游標新的那些，游標每輪推進），不會隨輪詢重複洗版。
 */
export function toBannerSeverity(raw: unknown): BannerSeverity {
  if (typeof raw === "string" && ALERT_SEVERITIES.includes(raw)) {
    return "alert";
  }
  if (!isAbsent(raw) && !(typeof raw === "string" && KNOWN_SEVERITIES.includes(raw))) {
    // 同 `elder/useTalk.ts`／`talk/qrScanner.ts` 既有的 `[前綴] 中文` 慣例。
    // 印出原值（不是只說「有問題」）——排查的人第一個要問的就是「那到底是什麼」。
    console.warn(
      "[notify] 認不得的通知分級，已保守降級為一般通知；" +
        "若後端新增了更嚴重的等級，需同步更新 notify/severity.ts 的對照表",
      raw,
    );
  }
  return "notice";
}

/** 型別出口：讓 `NotificationSeverity` 在 web 內部也取用得到，不必每處都從 shared 匯入。 */
export type { NotificationSeverity };
