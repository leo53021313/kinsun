/** 運營狀態卡：整體狀態一句話＋逐項燈號＋受限時的白話說明。 */

import { strings } from "@/strings";

import type { GateState } from "./useDemoStatus";

const DOT: Record<string, string> = {
  ok: "bg-success",
  loading: "bg-primary animate-pulse",
  down: "bg-danger",
  unknown: "bg-line",
};

export function StatusCard(props: { state: GateState }) {
  const { status, unreachable } = props.state;

  if (unreachable) {
    return (
      <p className="text-center text-lg text-danger">{strings.gate.statusUnreachable}</p>
    );
  }
  if (status === null) {
    return <p className="text-center text-lg text-ink-soft">{strings.gate.checking}</p>;
  }

  const notes = Object.entries(status.components)
    .filter(([, value]) => value === "down")
    .map(([name]) => strings.gate.degradedNote[name])
    .filter(Boolean);

  return (
    <div className="w-full max-w-md rounded-3xl border border-line bg-surface p-6 shadow-sm">
      <p className="text-center text-xl font-bold text-ink">
        {strings.gate.overall[status.overall] ?? status.overall}
      </p>
      <ul className="mt-5 space-y-2">
        {Object.entries(status.components).map(([name, value]) => (
          <li key={name} className="flex items-center justify-between text-base">
            <span className="flex items-center gap-2 text-ink">
              <span
                aria-hidden
                className={`inline-block size-2.5 rounded-full ${DOT[value] ?? DOT.unknown}`}
              />
              {strings.gate.component[name] ?? name}
            </span>
            <span className="text-ink-soft">
              {strings.gate.componentStatus[value] ?? value}
            </span>
          </li>
        ))}
      </ul>
      {notes.length > 0 ? (
        <div className="mt-5 space-y-1 rounded-2xl bg-background p-4">
          {notes.map((note) => (
            <p key={note} className="text-sm text-ink-soft">
              {note}
            </p>
          ))}
        </div>
      ) : null}
    </div>
  );
}
