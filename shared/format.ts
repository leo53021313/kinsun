/** 三端共用時間／延遲格式化（✅ D-51，乙-5）：epoch 秒進、台灣慣用字串出。 */

/** M/D HH:mm（列表、通知用的短格式）。 */
export function formatTime(epochSeconds: number): string {
  const d = new Date(epochSeconds * 1000);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${d.getMonth() + 1}/${d.getDate()} ${hh}:${mm}`;
}

/** 完整日期時間（zh-TW、24 小時制）。 */
export function formatDateTime(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toLocaleString("zh-TW", { hour12: false });
}

/** 只取時分秒（時間軸用）。 */
export function formatClock(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toLocaleTimeString("zh-TW", { hour12: false });
}

export function formatLatency(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)} 秒` : `${ms} 毫秒`;
}
