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

/**
 * 一段長度（秒）轉人看得懂的講法：`90` → 「1 分 30 秒」、`46800` → 「13 小時」。
 *
 * 只取最大的兩級單位——排程逾期告警要能一眼判斷嚴重程度，
 * 「1123200 秒」沒有人算得出那是十三天。
 */
export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} 秒`;
  if (s < 3600) {
    const rest = s % 60;
    return rest ? `${Math.floor(s / 60)} 分 ${rest} 秒` : `${Math.floor(s / 60)} 分`;
  }
  if (s < 86400) {
    const rest = Math.floor((s % 3600) / 60);
    return rest ? `${Math.floor(s / 3600)} 小時 ${rest} 分` : `${Math.floor(s / 3600)} 小時`;
  }
  const rest = Math.floor((s % 86400) / 3600);
  return rest ? `${Math.floor(s / 86400)} 天 ${rest} 小時` : `${Math.floor(s / 86400)} 天`;
}
