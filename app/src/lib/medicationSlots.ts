/** 用藥時段字典：值與後端 MedicationSlot enum 一致（比照 LIFF frontend/src/medicationSlots.ts）。 */

export const SLOTS = [
  { value: "morning", label: "早上" },
  { value: "noon", label: "中午" },
  { value: "evening", label: "晚上" },
  { value: "bedtime", label: "睡前" },
] as const;

export function slotLabel(value: string): string {
  return SLOTS.find((s) => s.value === value)?.label ?? value;
}
