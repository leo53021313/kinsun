/** 開場：先看服務狀態，可用才讓人進去（spec §5.1）。 */

import { strings } from "@/strings";

import { StatusCard } from "./StatusCard";
import { canEnter, useDemoStatus } from "./useDemoStatus";

export function GatePage(props: { onStart: () => void }) {
  const state = useDemoStatus();
  const enterable = canEnter(state);

  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-8 bg-background p-8">
      <div className="text-center">
        <h1 className="text-elder-huge font-extrabold text-primary">{strings.gate.brand}</h1>
        <p className="mt-2 text-base text-ink-soft">{strings.gate.slogan}</p>
      </div>

      <StatusCard state={state} />

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
