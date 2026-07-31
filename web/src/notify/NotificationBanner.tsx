/**
 * 模擬的系統通知橫幅（W-13）。
 *
 * ⚠️ 這是**畫面上的模擬**，不是瀏覽器的 Notification API：後端只支援 Expo 推播
 * （`src/kinsun/web/routers/push_tokens.py` 的平台白名單只有 android／ios），網頁沒有
 * 那條路，而做 Web Push 是一整包新的後端工作（VAPID＋Service Worker＋金鑰管理）。
 * 展示要的正是「手機上跳出通知」的那個畫面感，模擬完全足夠。
 *
 * ⚠️ **live region 掛在 `stage/PhoneFrame.tsx` 的通知容身處，不在本元件自己身上**
 * （審查修正，2026-07-31）：本元件會隨 `item` 整顆掛載／卸載（`key` 綁 `item.id`），
 * 若 `role="status"` 也掛在這裡，容器與內容會在同一次 DOM 變更一起冒出來——AT
 * 必須先「看見」live region 存在才會追蹤後續文字變化，這是最常見的 live region
 * 失效形狀。真實播報是否如預期仍待真機讀螢幕軟體驗收，這裡只保證用的是正確
 * 的形狀（`docs/dev/*` 三處文件已從「已解決」改寫為「已採用正確形狀，實際播報
 * 待真機驗收」，不宣稱沒有實測過的事）。
 *
 * ⚠️ 刻意用 `aria-live="polite"`（不是「打斷你」）：`ui/Feedback.tsx` 已把這個
 * 分工寫清楚——`polite` 是「禮貌宣告、等目前朗讀結束才播報」，`assertive`／
 * `role="alert"` 才是打斷。用藥提醒等一般通知走 polite 是對的；`BannerItem`
 * 新增的 `severity` 欄位是為了未來的危急警報鋪路，不是本元件現在會自產 alert。
 *
 * ⚠️ 尊重 prefers-reduced-motion（W-11）：判斷式抽到 `stage/reducedMotion.ts`，
 * 與 `stage/TearTransition.tsx` 共用同一份、用法也對齊——皆在掛載當下用
 * `useState` 讀一次、之後凍結。本元件因 `key` 每次 `item.id` 改變都會重新掛載，
 * 所以「掛載時讀一次」與「每次 render 都讀」在這裡結果相同，但寫法對齊比較
 * 不會誤導以後同時讀這兩個檔案的人。
 *
 * ⚠️ 本元件不管理佇列：連續來好幾則時，後面那則直接取代前面那則、重新播一次
 * 進場動畫（`key` 綁 `item.id`）。要不要排隊、疊圖，是資料來源呼叫端的責任，
 * 不是這顆純展示元件的——呼叫端是 `stage/StagePage.tsx`（P4 Task 4，2026-08-01
 * 接上，見該檔），佇列邏輯住在 `notify/useNotificationFeed.ts`。
 */

import { useState } from "react";

import { strings } from "@/strings";

import { prefersReducedMotion } from "../stage/reducedMotion";
import type { PhoneOs } from "./osStyle";

export type BannerItem = {
  id: string;
  title: string;
  content: string;
  at: number;
  /**
   * 通知的嚴重度：`"notice"`（預設，一般提醒／關懷，禮貌宣告）或 `"alert"`
   * （危急警報）。
   *
   * ⚠️ **目前仍只是型別預留，`stage/StagePage.tsx`（P4 Task 4）接上真實資料
   * 來源之後也一律不傳這個欄位、恆為預設值 `"notice"`——這不是「還沒接」，
   * 是刻意不接，且短期內不會有人接：後端 `app_notifications` 資料表（見
   * `src/kinsun/notifications/store.py::AppNotification`）與
   * `kinsun-shared/types.ts::AppNotification` 型別都只有 `content`／
   * `created_at` 兩個欄位，沒有任何分類欄位可以分辨「這是危急警報」還是
   * 「這是一般提醒」。危急事件與一般提醒目前寫進同一張表，寫入時就沒有
   * 留下分類線索。
   *
   * ⚠️ **看到這裡想「用 `content` 字串比對關鍵字（如『跌倒』『危急』）湊一個
   * `severity` 出來」之前，請先讀這句**：那是臆測而非真實訊號，會讓「什麼算
   * 危急」這個判斷散落在展示用的前端字串比對邏輯裡，而不是後端 `safety/`
   * 模組已有的權威分級結果——這正是本檔（見上方）「不追加沒有真實呼叫端的
   * 推測性 wiring」要擋住的事，也是 AGENTS.md「資訊不足時不要自行猜測」的
   * 具體案例。是否要在後端加分類欄位，待 Leo 裁決（見 `docs/dev/12` §4／
   * `07` §7 的完整討論）。
   *
   * `stage/PhoneFrame.tsx` 的通知容身處目前固定宣告 `role="status"`／
   * `aria-live="polite"`，也還沒有依這個欄位動態切換 `role="alert"`／
   * `aria-live="assertive"` 的邏輯——真的決定要接的話，那邊需要一併補上
   * （換同一個節點的屬性值，不是整個重新掛載，AT 仍追得到）。
   */
  severity?: "notice" | "alert";
};

const STYLE: Record<PhoneOs, string> = {
  // iOS：毛玻璃、大圓角、置中偏上。
  ios: "rounded-3xl bg-white/80 backdrop-blur-md shadow-lg ring-1 ring-black/5",
  // Android：Material 卡片、較小圓角、實色。
  android: "rounded-2xl bg-surface shadow-xl border border-line",
};

/**
 * 字級依 `size` 放大（同 `ui/ErrorText`／`ui/Field` 既有的 `size` prop 修法）。
 *
 * ⚠️ 審查發現：brief 原始版本標題／內容固定 12px／14px，低於長輩端
 * `--text-elder-min`（22px）下限。這張橫幅一旦被塞進長輩欄，恰好是長輩該讀
 * 的那句話（如「提醒您：降血壓藥」）卻小到看不清——同一個坑 `TalkScreen.tsx`
 * 的未讀紅點已經開過一次（`ElderApp` 寫死 `unread={0}` 時沒人會發現字級不夠
 * 大，等真的接上輪詢才現形），這裡不要重演同一種「還沒接線所以先放著」的推遲。
 */
const TEXT_SIZE = {
  normal: { title: "text-xs", content: "text-sm leading-5" },
  big: { title: "text-elder-min", content: "text-elder-min leading-relaxed" },
} as const;

/**
 * 關閉鍵的可點擊目標依 `size` 放大：`normal` 48px（`ui/Button.tsx` 既有的一般
 * 下限，WCAG 2.5.5 建議的 44px 以上）、`big` 56px（同 `elder/TalkScreen.tsx`
 * 鈴鐺與登出鍵既有的長輩端下限）。
 *
 * ⚠️ 審查發現：brief 原始版本沒有任何 `min-h`／`size`，父層 `items-start` 下
 * 實際高度只有 `text-lg`（18px）×`leading-none`（1）＝約 18px、寬度約 28px
 * ——連 WCAG 2.5.5 的 44px 都差得遠，長輩想關掉擋住畫面的橫幅時很可能點不到。
 */
const DISMISS_SIZE = {
  normal: "size-12 text-lg",
  big: "size-14 text-2xl",
} as const;

export function NotificationBanner(props: {
  item: BannerItem | null;
  os: PhoneOs;
  onDismiss: () => void;
  /** 長輩欄用 `"big"` 放大字級與關閉鍵；家屬欄沿用預設 `"normal"`。 */
  size?: "normal" | "big";
}) {
  const { item, os, onDismiss, size = "normal" } = props;
  // ⚠️ 呼叫順序須在下方的提前 return 之前：item 在 null／非 null 之間切換時，
  // 同一個元件實例不能出現「有時呼叫、有時不呼叫」的 hook，否則違反 React 的
  // Hooks 規則（與 stage/TearTransition.tsx 的既有寫法一致）。
  const [reduced] = useState(prefersReducedMotion);
  if (item === null) {
    return null;
  }
  const text = TEXT_SIZE[size];
  return (
    <div
      // ⚠️ key 用 item.id：沒有它的話 React 會沿用同一個 DOM 節點，第二則會靜靜地
      // 換掉字、完全沒有「又來一則」的感覺——而那正是展示要的效果。
      key={item.id}
      data-testid="notification-banner"
      // ⚠️ 卡片本體維持 pointer-events-none（審查發現的 Minor）：橫幅從
      // PhoneFrame 的 y=40px 起、高約 62px，恰好整條蓋住長輩欄的鈴鐺列（56px）
      // 與登出鍵——只讓下面的關閉鍵自己 pointer-events-auto，卡片其餘範圍的
      // 點擊會穿透到底下真正的按鈕。
      className={`pointer-events-none flex items-start gap-2 p-3 ${
        reduced ? "" : "animate-[slideDown_240ms_ease-out]"
      } ${STYLE[os]}`}
    >
      <div className="min-w-0 flex-1">
        <p className={`font-bold text-ink ${text.title}`}>{item.title}</p>
        <p className={`mt-0.5 break-words text-ink ${text.content}`}>{item.content}</p>
      </div>
      <button
        type="button"
        aria-label={strings.common.close}
        onClick={onDismiss}
        className={`pointer-events-auto flex shrink-0 items-center justify-center rounded-full leading-none text-ink-soft ${DISMISS_SIZE[size]}`}
      >
        ×
      </button>
    </div>
  );
}
