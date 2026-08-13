/** 開場：先看服務狀態，可用才讓人進去（spec §5.1）。
 *
 * ⚠️ **純展示元件**：狀態由 props 收，不自己呼叫 `useDemoStatus`。轉場動畫啟動時
 * 本元件會被卸載、在 overlay 底下重掛一份（見 BloomTransition），狀態若住在這裡，
 * 動畫開始的瞬間就會歸零成「正在確認服務狀態…」。狀態的擁有者是 App.tsx 的 Demo。
 */

import type { BloomOrigin } from "@/stage/BloomTransition";
import { strings } from "@/strings";

import { StatusCard } from "./StatusCard";
import { canEnter, type GateState } from "./useDemoStatus";

/**
 * 光暈的圓心＝按鈕中心。
 *
 * ⚠️ **不可用 `event.clientX`／`clientY`**：鍵盤按 Enter／Space 觸發 click 時兩者
 * 都是 `0`，光暈會從畫面左上角冒出來。`getBoundingClientRect()` 對滑鼠、觸控、
 * 鍵盤三種操作都給同一個正確答案。
 */
function centerOf(element: HTMLElement): BloomOrigin {
  const rect = element.getBoundingClientRect();
  return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
}

export function GatePage(props: { state: GateState; onStart: (origin: BloomOrigin) => void }) {
  const enterable = canEnter(props.state);

  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-8 bg-background p-8">
      <div className="text-center">
        <h1 className="text-elder-huge font-extrabold text-primary">{strings.gate.brand}</h1>
        <p className="mt-2 text-base text-ink-soft">{strings.gate.slogan}</p>
      </div>

      <StatusCard state={props.state} />

      <button
        type="button"
        disabled={!enterable}
        onClick={(event) => props.onStart(centerOf(event.currentTarget))}
        className="min-h-14 rounded-2xl bg-primary px-10 text-lg font-bold text-white transition-colors enabled:hover:bg-primary-pressed disabled:cursor-not-allowed disabled:opacity-40"
      >
        {strings.gate.start}
      </button>
    </main>
  );
}
