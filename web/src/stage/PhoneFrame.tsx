/**
 * 手機外框（spec §5.3）：讓觀眾一眼看出「這是長輩看到的、那是家屬看到的」。
 *
 * ⚠️ 狀態列的時間是**固定的 9:41**，不是真的時鐘：展示畫面上跳動的數字會把
 * 觀眾的注意力吸走，而且每張截圖都會不一樣。
 *
 * ⚠️ 通知橫幅由呼叫端以 notificationSlot 注入，本元件不知道通知是怎麼來的
 * ——外框只負責「有一個地方可以放它」，這樣外框可以完全獨立測試。
 *
 * ⚠️ 通知容身處的 live region 掛在本元件（審查修正，2026-07-31）：這個容器從
 * `PhoneFrame` 掛載那一刻就存在，不管 `notificationSlot` 傳了什麼、有沒有內容
 * 都不會被卸載重掛。輔助科技必須先「看見」live region 存在，才會追蹤它之後的
 * 文字變化——若把這個屬性掛在隨通知出現／消失而整顆掛載／卸載的元件上
 * （`notify/NotificationBanner.tsx` 曾經的作法），容器與內容會在同一次 DOM
 * 變更一起冒出來，AT 收到的是「新元素出現」而非「我在追蹤的區域文字變了」，
 * 多數 AT 因此不會播報。
 *
 * ⚠️ **`notificationSeverity` 切換的是同一個節點的屬性值，不是換一顆容器**
 * （2026-08-01，後端 `severity` 欄到位後接上）：危急警報要 `role="alert"`／
 * `aria-live="assertive"`（打斷目前朗讀），一般提醒維持 `role="status"`／
 * `aria-live="polite"`。刻意不改成「渲染兩顆容器、依 severity 擇一」——那會讓
 * 容器在切換時掛載／卸載，正好回到上一段修掉的那個失效形狀。
 *
 * ⚠️ **已知殘留風險（誠實載明，未經真機驗收）**：在**同一次 DOM 變更**裡既改
 * `aria-live` 又塞進內容，部分 AT 可能沿用變更前的值播報（它們對 live region
 * 屬性的重新評估時機不一致）。更保險的形狀是「polite 與 assertive 兩顆容器
 * 都常駐、內容渲染進對應那顆」，但那與上一段「容器不可隨通知增減」的既有
 * 結論會多一層互動，且本專案至今沒有真機讀螢幕軟體的驗收管道。這裡採用
 * 裁決指定的屬性切換形狀，並把不確定性寫在這裡——**不宣稱播報行為已經驗證過**。
 * `docs/dev/12` §4 已記入待真機驗收項。
 */

import type { ReactNode } from "react";

import type { BannerSeverity } from "../notify/severity";

export type PhoneOs = "ios" | "android";

/** 展示用的固定時間。取 Apple 主視覺慣用的 9:41。 */
const STATUS_TIME = "9:41";

export function PhoneFrame(props: {
  title: string;
  os: PhoneOs;
  notificationSlot?: ReactNode;
  /**
   * 目前放在容身處那一則的呈現分級，決定 live region 的宣告強度。
   *
   * ⚠️ 它與 `notificationSlot` 必須來自**同一則通知**——呼叫端兩個都要傳
   * （見 `StagePage.tsx`）。只傳 slot 不傳這個，讀螢幕的人會用禮貌語氣聽到
   * 危急警報；只傳這個不傳 slot，容器是空的、什麼都不會播。
   *
   * 沒有通知時傳什麼都無所謂（容器是空的），故為選填、預設 `"notice"`。
   */
  notificationSeverity?: BannerSeverity;
  children: ReactNode;
}) {
  const { title, os, notificationSlot, notificationSeverity = "notice", children } = props;
  const isAlert = notificationSeverity === "alert";
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

      {/* 通知橫幅的容身處：絕對定位疊在內容之上，不擠壓版面。live region 的
          role／aria-live 依 notificationSeverity 切換，見上方檔案說明。 */}
      <div
        role={isAlert ? "alert" : "status"}
        aria-live={isAlert ? "assertive" : "polite"}
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
