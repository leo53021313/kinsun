/**
 * 模擬的系統通知橫幅（W-13）。
 *
 * ⚠️ 這是**畫面上的模擬**，不是瀏覽器的 Notification API：後端只支援 Expo 推播
 * （`src/kinsun/web/routers/push_tokens.py` 的平台白名單只有 android／ios），網頁沒有
 * 那條路，而做 Web Push 是一整包新的後端工作（VAPID＋Service Worker＋金鑰管理）。
 * 展示要的正是「手機上跳出通知」的那個畫面感，模擬完全足夠。
 *
 * ⚠️ 用 role="status"：通知的重點就是「打斷你、讓你知道」。只有視覺效果的話，
 * 對用讀螢幕的人等於這則通知不存在。`role="status"` 隱含 `aria-live="polite"`，
 * 不需另外宣告；也刻意不宣告 `aria-modal`——這不是模態視窗，橫幅出現時長輩仍能
 * 繼續按麥克風、家屬仍能繼續操作其他欄位（這份 spec 抓到過宣告了 `aria-modal`
 * 卻沒有對應模態性的問題）。
 *
 * ⚠️ 尊重 prefers-reduced-motion（W-11）：做法與 `stage/TearTransition.tsx` 一致，
 * 以 `matchMedia` 在 JS 層判斷是否要套用滑入動畫的類名，而**不是**在 CSS 寫
 * `@media (prefers-reduced-motion: reduce)` 覆蓋——後者在 jsdom 測不到，會讓這個
 * 無障礙承諾整個只靠人工留守（本專案對動態效果的既有慣例是可測試的 JS 判斷）。
 *
 * ⚠️ 本元件不管理佇列：連續來好幾則時，後面那則直接取代前面那則、重新播一次
 * 進場動畫（`key` 綁 `item.id`）。要不要排隊、疊圖，是未來資料來源呼叫端的責任，
 * 不是這顆純展示元件的——目前尚未接上任何資料來源。
 */

import { strings } from "@/strings";

import type { PhoneOs } from "./osStyle";

export type BannerItem = {
  id: string;
  title: string;
  content: string;
  at: number;
};

const STYLE: Record<PhoneOs, string> = {
  // iOS：毛玻璃、大圓角、置中偏上。
  ios: "rounded-3xl bg-white/80 backdrop-blur-md shadow-lg ring-1 ring-black/5",
  // Android：Material 卡片、較小圓角、實色。
  android: "rounded-2xl bg-surface shadow-xl border border-line",
};

/** 同 `stage/TearTransition.tsx` 既有的判斷式，僅本檔獨立一份（兩者各自是自成
 * 一體的動畫模組，同 `elder/api.ts` 與 `talk/talkSocket.ts` 各自宣告 `ElderPlace`
 * 的既有前例）。*/
function prefersReducedMotion(): boolean {
  return typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function NotificationBanner(props: {
  item: BannerItem | null;
  os: PhoneOs;
  onDismiss: () => void;
}) {
  const { item, os, onDismiss } = props;
  if (item === null) {
    return null;
  }
  const reduced = prefersReducedMotion();
  return (
    <div
      // ⚠️ key 用 item.id：沒有它的話 React 會沿用同一個 DOM 節點，第二則會靜靜地
      // 換掉字、完全沒有「又來一則」的感覺——而那正是展示要的效果。
      key={item.id}
      role="status"
      className={`pointer-events-auto flex items-start gap-2 p-3 ${
        reduced ? "" : "animate-[slideDown_240ms_ease-out]"
      } ${STYLE[os]}`}
    >
      <div className="min-w-0 flex-1">
        <p className="text-xs font-bold text-ink">{item.title}</p>
        <p className="mt-0.5 break-words text-sm leading-5 text-ink">{item.content}</p>
      </div>
      <button
        type="button"
        aria-label={strings.common.close}
        onClick={onDismiss}
        className="shrink-0 rounded-full px-2 text-lg leading-none text-ink-soft"
      >
        ×
      </button>
    </div>
  );
}
