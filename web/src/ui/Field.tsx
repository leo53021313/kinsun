/** 兩欄共用的表單欄位。標籤與輸入框以 useId 連起來。 */

import { useId } from "react";

export function Field(props: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: "text" | "password" | "email" | "tel";
  placeholder?: string;
  size?: "normal" | "big";
  autoComplete?: string;
}) {
  const { label, value, onChange, type = "text", placeholder, size = "normal", autoComplete } = props;
  // ⚠️ 用 useId 而非寫死 id：同一個畫面上兩個同名欄位（密碼／確認密碼）若 id 相同，
  // 點標籤永遠聚焦到第一個，而那種 bug 用眼睛看不出來。
  const id = useId();
  // ⚠️ 長輩端審查發現：標籤原本固定 `text-sm`（14px），不隨 `size="big"` 放大
  // ——輸入框內文是 22px，但「綁定碼」「手機號碼」「密碼」這些一直掛在畫面上
  // 的標籤反而是全畫面最小的字。家屬端（`size` 預設 `"normal"`）不受影響。
  const labelSizeClass = size === "big" ? "text-elder-min" : "text-sm";
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className={`font-semibold text-ink-soft ${labelSizeClass}`}>
        {label}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        placeholder={placeholder}
        autoComplete={autoComplete}
        onChange={(event) => onChange(event.target.value)}
        className={`rounded-xl border border-line bg-surface px-4 text-ink placeholder:text-ink-soft ${
          size === "big" ? "min-h-14 text-elder-min" : "min-h-12 text-base"
        }`}
      />
    </div>
  );
}
