/** 開場：先看服務狀態，可用才讓人進去（spec §5.1）。
 *
 * ⚠️ **純展示元件**：狀態由 props 收，不自己呼叫 `useDemoStatus`。撕裂動畫啟動時
 * 本元件會被卸載、在 overlay 底下重掛兩份（見 TearTransition），狀態若住在這裡，
 * 撕開的瞬間就會歸零成「正在確認服務狀態…」。狀態的擁有者是 App.tsx 的 Demo。
 */

import { strings } from "@/strings";

import { StatusCard } from "./StatusCard";
import { canEnter, type GateState } from "./useDemoStatus";

export function GatePage(props: { state: GateState; onStart: () => void }) {
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
        onClick={props.onStart}
        className="min-h-14 rounded-2xl bg-primary px-10 text-lg font-bold text-white transition-colors enabled:hover:bg-primary-pressed disabled:cursor-not-allowed disabled:opacity-40"
      >
        {strings.gate.start}
      </button>
    </main>
  );
}
