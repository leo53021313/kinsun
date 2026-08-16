/**
 * 「之前聊過的」：長輩端的當日對話（W4）。
 *
 * ## 三個設計決定（沿用 App 批次 4）
 *
 * **只留當天。** 跨日自動視為空（`todayLog` 比對 `day` 欄位），不必等清除排程。
 * 底部那句「只留今天的，明天就換新的了」是講給長輩聽的，不是免責聲明。
 *
 * **最新的在最上面。** 長輩要找的通常是剛才那句，不是今天第一句。
 *
 * **沒有「再聽一次」。** 依 2026-08-07 使用者選項 1：`TodayTurn` 還沒有可持久化的
 * 音檔識別，也沒有重新合成的契約。不留空函式或按了沒反應的鈕——那比沒有更糟。
 *
 * ⚠️ **不打後端。** 資料源是本機的 `todayLog`，逐字內容只存在長輩自己的裝置。
 *
 * ⚠️ 版面與對講機同一套規矩：頁首固定，**只有內容層可捲**。長輩不一定知道要滑，
 * 但一天講幾十輪時清單一定超過一屏——這是規則 2 明文的例外（內容層），不是違反。
 */

import { useEffect, useState } from "react";

import { strings } from "@/strings";

import { BearAvatar } from "./BearStage";
import { loadToday, type TodayTurn } from "./todayLog";

/** 「早上 9:05」這種長輩讀得懂的說法，不用 24 小時制。 */
function formatHistoryTime(at: number): string {
  const date = new Date(at);
  const hour = date.getHours();
  const minute = String(date.getMinutes()).padStart(2, "0");
  const period = hour < 12 ? "早上" : hour < 18 ? "下午" : "晚上";
  const hour12 = hour % 12 === 0 ? 12 : hour % 12;
  return `${period} ${hour12}:${minute}`;
}

export function HistoryScreen(props: { onBack: () => void }) {
  const [turns, setTurns] = useState<TodayTurn[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let alive = true;
    void loadToday().then((list) => {
      if (alive) {
        setTurns(list);
        setLoaded(true);
      }
    });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="elder-gradient flex h-full flex-col">
      {/* 頁首固定：60dp 圓形返回鈕＋標題。與對講機頁一致，不用 ElderApp 的共用返回列。 */}
      <div className="flex shrink-0 items-center gap-4 px-[var(--size-elder-page-padding)] pb-4 pt-3">
        <button
          type="button"
          onClick={props.onBack}
          aria-label={strings.elderHistory.back}
          className="flex size-[var(--size-elder-round-button)] shrink-0 items-center justify-center rounded-full border border-line bg-surface text-3xl text-primary shadow-[var(--elevation-row)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          <span aria-hidden>‹</span>
        </button>
        <h1 className="flex-1 text-[28px] font-extrabold text-ink">
          {strings.elderHistory.title}
        </h1>
        {/* 阿白也在這一頁——他不是只存在於對講機那一格畫面裡。 */}
        <BearAvatar />
      </div>

      {/* 內容層：只有這一塊捲。 */}
      <div
        data-testid="history-list"
        className="flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto px-[var(--size-elder-page-padding)] pb-10"
      >
        {loaded && turns.length === 0 ? (
          <p className="text-elder-min leading-relaxed text-ink-soft">
            {strings.elderHistory.empty}
          </p>
        ) : null}

        {/* 反轉副本，最新一輪在最上面。不可直接 `reverse()`——那會就地改動 state。 */}
        {[...turns].reverse().map((turn, index) => (
          <div
            key={`${turn.at}:${index}`}
            data-testid={`history-turn-${index}`}
            className="flex flex-col gap-1 rounded-card border border-line bg-surface p-4 shadow-[var(--elevation-row)]"
          >
            <p className="text-elder-min text-ink-soft">{formatHistoryTime(turn.at)}</p>
            <p className="text-elder-min font-bold leading-relaxed text-ink-soft">
              {strings.elderHistory.youSaid}
              {turn.said}
            </p>
            <p className="text-elder-min font-bold leading-relaxed text-ink">
              {strings.elderHistory.bearSaid}
              {turn.reply}
            </p>
          </div>
        ))}

        {turns.length > 0 ? (
          <p className="pt-2 text-elder-min text-ink-soft">{strings.elderHistory.footnote}</p>
        ) : null}
      </div>
    </div>
  );
}
