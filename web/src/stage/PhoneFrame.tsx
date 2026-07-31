/**
 * 手機外框（spec §5.3）：讓觀眾一眼看出「這是長輩看到的、那是家屬看到的」。
 *
 * ⚠️ 狀態列的時間是**固定的 9:41**，不是真的時鐘：展示畫面上跳動的數字會把
 * 觀眾的注意力吸走，而且每張截圖都會不一樣。
 *
 * ⚠️ 通知橫幅由呼叫端以 notificationSlot 注入，本元件不知道通知是怎麼來的
 * ——外框只負責「有一個地方可以放它」，這樣外框可以完全獨立測試。
 *
 * ⚠️ 通知容身處的 `role="status"`／`aria-live="polite"` 掛在本元件（審查修正，
 * 2026-07-31）：這個容器從 `PhoneFrame` 掛載那一刻就存在，不管
 * `notificationSlot` 傳了什麼、有沒有內容都不會被卸載重掛。輔助科技必須先
 * 「看見」live region 存在，才會追蹤它之後的文字變化——若把這個屬性掛在隨
 * 通知出現／消失而整顆掛載／卸載的元件上（`notify/NotificationBanner.tsx`
 * 曾經的作法），容器與內容會在同一次 DOM 變更一起冒出來，AT 收到的是「新元素
 * 出現」而非「我在追蹤的區域文字變了」，多數 AT 因此不會播報。
 */

import type { ReactNode } from "react";

export type PhoneOs = "ios" | "android";

/** 展示用的固定時間。取 Apple 主視覺慣用的 9:41。 */
const STATUS_TIME = "9:41";

export function PhoneFrame(props: {
  title: string;
  os: PhoneOs;
  notificationSlot?: ReactNode;
  children: ReactNode;
}) {
  const { title, os, notificationSlot, children } = props;
  return (
    <section
      aria-label={title}
      className="relative mx-auto flex aspect-[9/19.5] w-full max-w-[380px] flex-col overflow-hidden rounded-[2.75rem] border-[10px] border-ink bg-background shadow-2xl"
    >
      {/* 狀態列 */}
      <div className="relative flex shrink-0 items-center justify-between px-6 pt-2 text-xs font-semibold text-ink">
        <span>{STATUS_TIME}</span>
        {os === "ios" ? (
          <span
            data-testid="dynamic-island"
            aria-hidden
            className="absolute left-1/2 top-1.5 h-6 w-24 -translate-x-1/2 rounded-full bg-ink"
          />
        ) : null}
        <span aria-hidden className="flex items-center gap-1">
          <span className="inline-block h-2.5 w-3.5 rounded-[2px] bg-ink" />
          <span className="inline-block h-2.5 w-5 rounded-[2px] border border-ink" />
        </span>
      </div>

      {/* 通知橫幅的容身處：絕對定位疊在內容之上，不擠壓版面。role="status"／
          aria-live="polite" 見上方檔案說明。 */}
      <div
        role="status"
        aria-live="polite"
        className="pointer-events-none absolute inset-x-0 top-10 z-20 px-3"
      >
        {notificationSlot}
      </div>

      {/* 內容區 */}
      <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>

      {/* home indicator */}
      <div className="flex shrink-0 justify-center pb-2 pt-1">
        <span aria-hidden className="h-1 w-28 rounded-full bg-ink/40" />
      </div>
    </section>
  );
}
