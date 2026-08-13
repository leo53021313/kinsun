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
 * ⚠️ live region 的 `polite`／`assertive` 分工（`ui/Feedback.tsx` 已寫清楚）：
 * `polite` 是「禮貌宣告、等目前朗讀結束才播報」，`assertive`／`role="alert"`
 * 才是打斷。用藥提醒等一般通知走 polite；危急警報走 assertive。
 * **切換的動作不在本元件身上**——live region 掛在 `stage/PhoneFrame.tsx` 那個
 * 永遠掛載的容身處（見上一段），呼叫端要把 `banner.severity` 一併傳給
 * `PhoneFrame` 的 `notificationSeverity`，本元件只負責視覺樣式（紅色）。
 * 兩者缺一：只有紅色＝看得見的人分得出來、讀螢幕的人分不出來；只有 assertive
 * ＝反過來。`stage/StagePage.tsx` 同時傳了兩個，`StagePage.test.tsx` 釘住這件事。
 *
 * ⚠️ 尊重 prefers-reduced-motion（W-11）：判斷式抽到 `stage/reducedMotion.ts`，
 * 與 `stage/BloomTransition.tsx` 共用同一份、用法也對齊——皆在掛載當下用
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
import type { BannerSeverity } from "./severity";

export type BannerItem = {
  id: string;
  title: string;
  content: string;
  at: number;
  /**
   * 通知的呈現分級：`"notice"`（預設，一般提醒／關懷）或 `"alert"`（危急警報）。
   *
   * ⚠️ **2026-08-01 起這是真實資料，不再是型別預留**：後端 `app_notifications`
   * 已有 `severity` 欄（Leo 裁決），由 `src/kinsun/safety/notifier.py` 在危急
   * 通報時寫入 `alert`——那是分級器與審核鏈給出的**權威**判定。
   * `notify/useNotificationFeed.ts` 從 API 讀出來、經 `notify/severity.ts`
   * 收斂後放進這個欄位。
   *
   * ⚠️ **不要用 `content` 字串比對關鍵字（如「跌倒」「危急」）自己湊一個出來**：
   * 那是臆測而非真實訊號，會讓「什麼算危急」的判斷散落在前端字串比對裡，而不是
   * 後端 `safety/` 模組已有的權威分級。這個欄位存在的全部意義就是不必那樣做。
   *
   * ⚠️ 欄位缺席（舊資料、後端尚未部署）時的處置**不在這裡**，在
   * `notify/severity.ts::toBannerSeverity`——收斂只做一次、只有一個地方，
   * 免得各處各自決定「沒有值算什麼」。
   */
  severity?: BannerSeverity;
};

/**
 * 危急警報的視覺樣式：紅底白字（`--color-danger`，theme.css 既有 token）。
 *
 * ⚠️ **為什麼整張卡片換色，而不是只加一條紅邊或一個紅色圖示**：這張橫幅在
 * 展示現場是**滑進來、3.5 秒後就消失**的，觀眾與家屬都是用餘光瞄到它。細部
 * 裝飾在那個時間尺度上等於不存在——要讓「危急」在半秒內傳達出去，只有整片
 * 色塊做得到。這也是本次裁決要解決的症狀本身（「在畫面上與『該吃藥了』毫無
 * 區別」）。
 *
 * ⚠️ 兩種 OS 共用同一組警報樣式：iOS 的毛玻璃與 Android 的實色卡片是「一般
 * 通知在該平台長什麼樣」的模擬，而危急警報要的是「一眼認出來」，跨平台一致
 * 反而正確——真實世界的 iOS 緊急警報（Emergency Alert）也不走一般通知樣式。
 *
 * 白字對 `#B91C1C` 底的對比 **6.47:1**——過 WCAG AA（4.5:1），**不過 AAA（7:1）**。
 * ⚠️ 這兩個數字是依 WCAG 2.x 相對亮度公式對 `theme.css` 的實際 token 實算的
 * （T3 審查更正，2026-08-01：原文寫「約 7.4:1，過 AA 與 AAA」，兩項都錯）。
 * **不要以為還有無障礙餘裕**——距離 AA 下限只剩 1.97，再縮小字級或改用半透明
 * 白（如 `text-white/80`）就會跌破 4.5:1。要動這組顏色請先重算。
 */
const ALERT_STYLE = "rounded-2xl bg-danger text-white shadow-xl ring-1 ring-black/10";

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
  // Hooks 規則（與 stage/BloomTransition.tsx 的既有寫法一致）。
  const [reduced] = useState(prefersReducedMotion);
  if (item === null) {
    return null;
  }
  const text = TEXT_SIZE[size];
  const isAlert = item.severity === "alert";
  // ⚠️ 文字顏色必須跟著卡片一起換：`text-ink`（近黑）壓在 `bg-danger`（深紅）上
  // 對比只有 2.70:1（實算），低於 WCAG AA 的 4.5:1——換了底色卻沒換字色，等於把
  // 最該讀得清楚的那一則變成最讀不清楚的。關閉鍵的 `text-ink-soft` 同理。
  const bodyColor = isAlert ? "text-white" : "text-ink";
  return (
    <div
      // ⚠️ key 用 item.id：沒有它的話 React 會沿用同一個 DOM 節點，第二則會靜靜地
      // 換掉字、完全沒有「又來一則」的感覺——而那正是展示要的效果。
      key={item.id}
      data-testid="notification-banner"
      data-severity={isAlert ? "alert" : "notice"}
      // ⚠️ 卡片本體維持 pointer-events-none（審查發現的 Minor）：橫幅從
      // PhoneFrame 的 y=40px 起、高約 62px，恰好整條蓋住長輩欄的鈴鐺列（56px）
      // 與登出鍵——只讓下面的關閉鍵自己 pointer-events-auto，卡片其餘範圍的
      // 點擊會穿透到底下真正的按鈕。
      //
      // ⚠️ 危急警報**不**套 OS 樣式（見 ALERT_STYLE 說明）：兩者都是背景色類名，
      // 疊在一起後誰贏取決於 Tailwind 產出的 CSS 順序，是一個看不出來的坑。
      className={`pointer-events-none flex items-start gap-2 p-3 ${
        reduced ? "" : "animate-[slideDown_240ms_ease-out]"
      } ${isAlert ? ALERT_STYLE : STYLE[os]}`}
    >
      <div className="min-w-0 flex-1">
        <p className={`font-bold ${bodyColor} ${text.title}`}>{item.title}</p>
        <p className={`mt-0.5 break-words ${bodyColor} ${text.content}`}>{item.content}</p>
      </div>
      <button
        type="button"
        aria-label={strings.common.close}
        onClick={onDismiss}
        className={`pointer-events-auto flex shrink-0 items-center justify-center rounded-full leading-none ${
          isAlert ? "text-white" : "text-ink-soft"
        } ${DISMISS_SIZE[size]}`}
      >
        ×
      </button>
    </div>
  );
}
