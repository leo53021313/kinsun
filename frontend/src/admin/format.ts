/** epoch 秒 → 台灣慣用時間字串。 */
export function formatTime(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toLocaleString("zh-TW", { hour12: false });
}

/** epoch 秒 → 只取時分秒（時間軸用）。 */
export function formatClock(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toLocaleTimeString("zh-TW", { hour12: false });
}

export function formatLatency(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)} 秒` : `${ms} 毫秒`;
}
