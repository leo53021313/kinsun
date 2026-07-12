/**
 * 三端共用用語字典（⏳ D-46，乙-5）：同一個概念三端同一個詞。
 * 終值經會-9 擱置——先沿用 App 現值；改版只動這裡。
 * 危急等級三級制（✅ D-72，己-4）：L2 為頂級；舊資料的 3 由後端讀取時夾回 2。
 */

export const TIER_LABELS: Record<number, string> = {
  0: "一般",
  1: "關注",
  2: "需留意",
};

export function tierLabel(tier: number): string {
  return TIER_LABELS[tier] ?? `L${tier}`;
}

/** 觀測後台用（✅ 庚-27／F-10）：保留 L 編號給維運精確溝通，並列家屬端詞彙。 */
export function adminTierLabel(tier: number): string {
  const label = TIER_LABELS[tier];
  return label ? `L${tier} ${label}` : `L${tier}`;
}

export const SLOTS = [
  { value: "morning", label: "早上" },
  { value: "noon", label: "中午" },
  { value: "evening", label: "晚上" },
  { value: "bedtime", label: "睡前" },
] as const;

export function slotLabel(value: string): string {
  return SLOTS.find((s) => s.value === value)?.label ?? value;
}
