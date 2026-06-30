export const SLOTS = [
  { value: "morning", label: "早上" },
  { value: "noon", label: "中午" },
  { value: "evening", label: "晚上" },
  { value: "bedtime", label: "睡前" },
] as const;

export function slotLabel(value: string): string {
  return SLOTS.find((s) => s.value === value)?.label ?? value;
}
