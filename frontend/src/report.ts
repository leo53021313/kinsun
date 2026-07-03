const TIER_LABELS: Record<number, string> = { 2: "警示", 3: "緊急" };
const KIND_LABELS: Record<string, string> = { medication: "用藥", appointment: "回診" };

export function tierLabel(tier: number): string {
  return TIER_LABELS[tier] ?? `L${tier}`;
}

export function kindLabel(kind: string): string {
  return KIND_LABELS[kind] ?? kind;
}

export function formatTime(epoch: number): string {
  return new Date(epoch * 1000).toLocaleString("zh-TW");
}
