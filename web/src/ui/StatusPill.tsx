/**
 * 狀態一律「顏色＋圖示＋文字」三重編碼，拿掉顏色仍讀得懂（鐵律 6）。
 *
 * 把三重編碼收成元件，避免每個畫面自己拼——每畫面自己拼的結果就是有的畫面
 * 只剩顏色。`icon` 由呼叫端傳，這裡只管配色與版面。
 *
 * ⚠️ 五組配色的色碼與 `app/src/components/ui.tsx` 的 `PILL_TONES` 逐一相同。
 * 兩端都是寫死的字面值——那三個底色（#EAF7F3／#FDF6DE／#FDF0F0）同時也是
 * `theme.css` 的 `--talk-speaking-pill`／`--talk-idle-pill`／`--talk-error-pill`，
 * 但語意不同（那是對講機狀態帶，這是用藥／提醒狀態），刻意不共用同一個 token。
 * 收攏成獨立的 pill token 是三端一起做的事，不在 web 這一側單獨發明。
 */

import type { ReactNode } from "react";

type Tone = "done" | "pending" | "overdue" | "critical" | "info";

const PILL_TONES: Record<Tone, { bg: string; fg: string }> = {
  done: { bg: "#EAF7F3", fg: "var(--color-success-text)" },
  pending: { bg: "#FDF6DE", fg: "var(--color-warning-text)" },
  overdue: { bg: "#FDF6DE", fg: "var(--color-warning-text)" },
  critical: { bg: "#FDF0F0", fg: "var(--color-danger-text)" },
  info: { bg: "var(--color-background)", fg: "var(--color-primary)" },
};

export function StatusPill(props: {
  tone: Tone;
  label: string;
  icon: ReactNode;
  size?: "normal" | "big";
}) {
  const { tone, label, icon, size = "normal" } = props;
  const tint = PILL_TONES[tone];
  return (
    <span
      className="inline-flex items-center gap-1.5 self-start rounded-pill px-3.5 py-1.5"
      style={{ backgroundColor: tint.bg }}
    >
      <span aria-hidden className="flex shrink-0 items-center" style={{ color: tint.fg }}>
        {icon}
      </span>
      <span
        className={`font-bold ${size === "big" ? "text-elder-min" : "text-[15px]"}`}
        style={{ color: tint.fg }}
      >
        {label}
      </span>
    </span>
  );
}
