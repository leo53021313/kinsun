/**
 * 卡片。新視覺（2026-08）：圓角 16 → 24，並加上柔和陰影——家屬端原本完全無陰影，
 * 只有 1px 邊。值與 `app/src/components/ui.tsx` 的 `section` 對齊。
 *
 * `inset` 是「凹一階」的內嵌區塊（綁定碼面板那種）：淡底、無邊框、圓角小一階、
 * 無陰影。它蓋在卡片裡面，再加陰影會變成兩層浮起來。
 */

import type { ReactNode } from "react";

export function Section(props: { title?: string; children: ReactNode; inset?: boolean }) {
  const { title, children, inset = false } = props;
  return (
    <section
      className={[
        "flex flex-col gap-2 p-4",
        inset
          ? "rounded-control bg-background"
          : "rounded-card border border-line bg-surface shadow-[var(--elevation-card)]",
      ].join(" ")}
    >
      {title ? <h2 className="text-xl font-bold text-ink">{title}</h2> : null}
      {children}
    </section>
  );
}
