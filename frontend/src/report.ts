/** 健康報告顯示用語：等級與時間轉出自三端共用字典（⏳ D-46，乙-5）。 */

export { formatDateTime as formatTime } from "kinsun-shared/format";
export { tierLabel } from "kinsun-shared/terms";

const KIND_LABELS: Record<string, string> = { medication: "用藥", appointment: "回診" };

export function kindLabel(kind: string): string {
  return KIND_LABELS[kind] ?? kind;
}
