/**
 * 兩欄共用的按鈕。長輩端以 size="big" 放大（適老化 ✅ D-48）。
 *
 * 新視覺（2026-08）：主鍵由磚橘底白字改成**暖黃底深靛藍字的膠囊**。值與規格
 * 與 `app/src/components/ui.tsx` 的 Button 對齊，兩端只差在 RN／Tailwind 的寫法。
 *
 * - 暖黃 `--color-action` 是每頁唯一主要行動，一律配 `--color-ink`，**不配白字**
 *   （鐵律 14）。白字在暖黃上只有 1.9:1。
 * - 破壞性動作的文字用 `--color-danger-text` 而非 `--color-danger`——後者是
 *   3.7:1，只能當邊界與圖示（鐵律 15）。
 * - busy 時**保留動作名稱**：舊版換成「…」，長輩與家屬都不知道剛才按的是什麼。
 */

type ButtonVariant = "primary" | "outline" | "subtle" | "danger";
type ButtonSize = "normal" | "big";

/** 一般 56px、長輩端 84px；48px 仍是所有可點區域的下限（✅ 庚-32／F-14）。 */
const SIZE_CLASS: Record<ButtonSize, string> = {
  normal: "min-h-14 px-6 text-lg",
  big: "min-h-21 px-6 text-elder-big",
};

const VARIANT_CLASS: Record<ButtonVariant, string> = {
  primary:
    "bg-action text-ink shadow-[var(--elevation-action)] enabled:hover:bg-action-pressed",
  outline: "border-2 border-primary bg-surface text-primary enabled:hover:bg-background",
  subtle: "bg-background text-primary enabled:hover:bg-line",
  danger: "border-2 border-danger bg-surface text-danger-text enabled:hover:bg-[#FDF0F0]",
};

export function Button(props: {
  label: string;
  onClick: () => void;
  size?: ButtonSize;
  /** primary＝暖黃主鍵（每頁唯一）；outline＝靛藍外框；subtle＝淡底次要；danger＝破壞性 */
  variant?: ButtonVariant;
  disabled?: boolean;
  busy?: boolean;
}) {
  const {
    label,
    onClick,
    size = "normal",
    variant = "primary",
    disabled = false,
    busy = false,
  } = props;
  // 忙碌中一併停用：家屬連按兩下「建立長輩檔案」會建出兩位長輩。
  const inert = disabled || busy;
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={inert}
      aria-busy={busy}
      className={[
        "flex w-full items-center justify-center gap-2 rounded-pill font-bold",
        // 按下＝換色＋縮放，不只換色（motion.press 120ms）。
        "transition-[background-color,transform] duration-[var(--motion-press)] active:scale-[0.98]",
        // focus：2px 靛藍描邊＋2px 外偏移。規格早就寫了，實作一直缺。
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
        SIZE_CLASS[size],
        VARIANT_CLASS[variant],
        inert ? "cursor-not-allowed opacity-50" : "",
      ].join(" ")}
    >
      {busy ? (
        <span
          aria-hidden
          className="size-5 shrink-0 animate-spin rounded-full border-2 border-current border-t-transparent"
        />
      ) : null}
      {label}
    </button>
  );
}
