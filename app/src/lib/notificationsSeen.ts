/** 通知已讀水位：以本機時間戳記錄「看到哪裡」，未讀數＝比水位新的通知數（✅ D-12）。 */

import * as SecureStore from "expo-secure-store";

const KEY = "kinsun_notifications_seen_at";

export async function loadSeenAt(): Promise<number> {
  const raw = await SecureStore.getItemAsync(KEY);
  const value = raw ? Number(raw) : 0;
  return Number.isFinite(value) ? value : 0;
}

export async function saveSeenAt(epochSeconds: number): Promise<void> {
  await SecureStore.setItemAsync(KEY, String(epochSeconds));
}
