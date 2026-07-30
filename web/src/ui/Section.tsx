import type { ReactNode } from "react";

export function Section(props: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2 rounded-2xl border border-line bg-surface p-4">
      <h2 className="text-base font-bold text-ink">{props.title}</h2>
      {props.children}
    </section>
  );
}
