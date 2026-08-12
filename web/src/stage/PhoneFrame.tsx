/**
 * 手機外框（spec §5.3）：讓觀眾一眼看出「這是長輩看到的、那是家屬看到的」。
 *
 * ## 尺寸＝iPhone 17／17 Pro 的實際畫面（2026-08-09 裁決）
 *
 * 螢幕區固定 **402 × 874 CSS px**（@3x，6.3 吋）。iPhone 17 與 17 Pro 的視埠相同，
 * 這個值同時涵蓋兩種「最新 iPhone」的讀法；17 Pro Max 是 440 × 956、Air 是
 * 420 × 912，要換只改下面那兩個數字。
 *
 * 原本是 `aspect-[9/19.5]` 配 `max-w-[380px]` 的通用直式比例——那不是任何一支真
 * 機的尺寸，版面在框裡看起來對、在真機上不一定對。改成真實視埠之後，框裡量到的
 * 位置就是長輩手機上量到的位置，這對 W3b 的「一屏不捲」是必要條件：那條規則要
 * 成立與否，取決於畫面到底有多高。
 *
 * ⚠️ 邊框用 `outline` 而非 `border`：Tailwind 的 preflight 把 box-sizing 設成
 * border-box，用 border 的話 10px 邊框會從 402 裡面吃掉，螢幕實際只剩 382。
 * outline 畫在框外、不進版面計算，402 × 874 才真的是 402 × 874。
 *
 * ⚠️ `max-w-full` 保留：組員拿手機開這個網址時視窗比 402 窄，等比縮小仍可用；
 * 只有在放得下的時候才是 1:1。
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
 * 都常駐、內容渲染進對應那顆」（⚠️ 那個形狀**不違反**上一段的既有結論——上一段
 * 講的是容器不可被「卸載」，兩顆永遠掛載的容器並不牴觸；T3 審查更正，原文把
 * 這寫成拒絕理由是錯的）。真正的理由只有一個：**本專案至今沒有真機讀螢幕軟體
 * 的驗收管道，把一個驗證不了的形狀換成另一個驗證不了的形狀，只是把不確定性
 * 搬家**。故採用裁決指定的屬性切換形狀，並把不確定性寫在這裡
 * ——**不宣稱播報行為已經驗證過**。
 * `docs/dev/12` §4 已記入待真機驗收項。
 */

import type { ReactNode } from "react";

import type { BannerSeverity } from "../notify/severity";

export type PhoneOs = "ios" | "android";

/** 展示用的固定時間。取 Apple 主視覺慣用的 9:41。 */
const STATUS_TIME = "9:41";

/** iPhone 17／17 Pro 的視埠（CSS px，@3x）。換機型只改這兩個值。 */
const SCREEN_W = 402;
const SCREEN_H = 874;

/**
 * 頂部與底部安全區。匯出是因為畫面層要用它換算設計稿座標——設計稿的 y 座標
 * 以**裝置畫面頂端**為原點（App 的對講機頁沒有包 SafeAreaView，狀態列是 OS
 * 疊在 app 之上），而本元件的內容區已經扣掉這兩段。見 `elder/TalkScreen.tsx`。
 */
export const PHONE_STATUS_BAR_H = 54;
export const PHONE_HOME_INDICATOR_H = 34;

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
      data-testid="phone-frame"
      style={{ width: SCREEN_W, aspectRatio: `${SCREEN_W} / ${SCREEN_H}` }}
      className="relative mx-auto flex max-w-full flex-col overflow-hidden rounded-[55px] bg-background outline outline-[10px] outline-ink shadow-2xl"
    >
      {/* 狀態列高度取 Dynamic Island 機型的頂部安全區（約 54px），下方內容區
          因此拿到的高度就是真機上 app 可用的高度。 */}
      <div
        style={{ height: PHONE_STATUS_BAR_H }}
        className="relative flex shrink-0 items-center justify-between px-8 pt-1 text-sm font-semibold text-ink">
        <span>{STATUS_TIME}</span>
        {os === "ios" ? (
          <span
            data-testid="dynamic-island"
            aria-hidden
            className="absolute left-1/2 top-[11px] h-[37px] w-[125px] -translate-x-1/2 rounded-full bg-ink"
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
        className="pointer-events-none absolute inset-x-0 top-[58px] z-20 px-3"
      >
        {notificationSlot}
      </div>

      {/* 內容區 */}
      {/* 內容區維持可捲：家屬端的清單本來就會超過一屏。長輩端的「一屏不捲」
          由畫面自己負責——`elder/TalkScreen.tsx` 是 `h-full overflow-hidden`
          的絕對定位版面，永遠不會撐出這個框，因此不需要在外框加一個開關。 */}
      <div data-testid="phone-content" className="relative min-h-0 flex-1 overflow-y-auto">
        {children}
      </div>

      {/* home indicator：34px 是 iOS 底部安全區的既定值；home indicator 本身 5 × 140。 */}
      <div
        style={{ height: PHONE_HOME_INDICATOR_H }}
        className="flex shrink-0 items-end justify-center pb-2"
      >
        <span aria-hidden className="h-[5px] w-[140px] rounded-full bg-ink/40" />
      </div>
    </section>
  );
}
