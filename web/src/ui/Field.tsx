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
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-semibold text-ink-soft">
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
