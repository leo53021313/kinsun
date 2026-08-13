/**
 * 可複選／單選的時段與類型選項。
 *
 * **強制 48px 觸控下限**——這是 09 §1.4 列的待修項：原本各畫面自寫的內嵌 chip
 * 只有 padding、沒有最小高度，實際約 43px，低於所有可點區域的下限（鐵律 4）。
 *
 * ⚠️ 選取狀態用 `aria-checked` 而非 `aria-selected`：radio 與 checkbox 兩種 role
 * 在 ARIA 都是用 `aria-checked`，`aria-selected` 是 option／tab／gridcell 用的，
 * 讀螢幕軟體不會把它當勾選狀態播報。（`app/src/components/ui.tsx` 的 Chip 目前
 * 兩種 role 都送 `selected`，那是從交付稿 `handoff/ui.tsx:182` 繼承下來的，已列
 * 在驗收報告裡待修；web 這一側直接做對，不跟著抄。）
 */

export function Chip(props: {
  label: string;
  selected: boolean;
  onClick: () => void;
  role?: "radio" | "checkbox";
  size?: "normal" | "big";
  /** 編輯既有行程時鎖住「類型」——中途改類型再送出，後端會因新舊欄位對不上而 400。 */
  disabled?: boolean;
}) {
  const {
    label,
    selected,
    onClick,
    role = "checkbox",
    size = "normal",
    disabled = false,
  } = props;
  return (
    <button
      type="button"
      role={role}
      aria-checked={selected}
      disabled={disabled}
      onClick={onClick}
      className={[
        "min-h-12 rounded-pill border px-4.5 font-semibold",
        "transition-colors duration-[var(--motion-press)]",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
        "disabled:cursor-not-allowed disabled:opacity-50",
        size === "big" ? "text-elder-min" : "text-[17px]",
        selected
          ? "border-primary-pressed bg-primary-pressed font-bold text-white"
          : "border-line bg-surface text-ink",
      ].join(" ")}
    >
      {label}
    </button>
  );
}
