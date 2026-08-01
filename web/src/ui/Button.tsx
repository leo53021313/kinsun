/** 兩欄共用的按鈕。長輩端以 size="big" 放大（適老化 ✅ D-48）。 */

export function Button(props: {
  label: string;
  onClick: () => void;
  size?: "normal" | "big";
  variant?: "primary" | "outline";
  disabled?: boolean;
  busy?: boolean;
}) {
  const { label, onClick, size = "normal", variant = "primary", disabled = false, busy = false } = props;
  // 忙碌中一併停用：家屬連按兩下「建立長輩檔案」會建出兩位長輩。
  const inert = disabled || busy;
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={inert}
      aria-busy={busy}
      className={[
        "w-full rounded-2xl font-bold transition-colors",
        // 48px 是可點擊目標的下限（✅ 庚-32／F-14）；長輩端再加大。
        size === "big" ? "min-h-16 text-elder-big" : "min-h-12 text-base",
        variant === "primary"
          ? "bg-primary text-white enabled:hover:bg-primary-pressed"
          : "border-2 border-primary bg-surface text-primary enabled:hover:bg-background",
        inert ? "cursor-not-allowed opacity-50" : "",
      ].join(" ")}
    >
      {busy ? "…" : label}
    </button>
  );
}
