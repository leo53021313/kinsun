/**
 * 手機外框（spec §5.3）：讓觀眾一眼看出「這是長輩看到的、那是家屬看到的」。
 *
 * ⚠️ 狀態列的時間是**固定的 9:41**，不是真的時鐘：展示畫面上跳動的數字會把
 * 觀眾的注意力吸走，而且每張截圖都會不一樣。
 *
 * ⚠️ 通知橫幅由呼叫端以 notificationSlot 注入，本元件不知道通知是怎麼來的
 * ——外框只負責「有一個地方可以放它」，這樣外框可以完全獨立測試。
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

      {/* 通知橫幅的容身處：絕對定位疊在內容之上，不擠壓版面。 */}
      <div className="pointer-events-none absolute inset-x-0 top-10 z-20 px-3">
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
