/** 通知已讀水位：以本機時間戳記錄「看到哪裡」，未讀數＝比水位新的通知數（✅ D-12）。
 *
 * 依角色分鍵（2026-07-29）：內測模式的「切換身分」讓同一台裝置會有兩種角色，
 * 共用一支鍵會讓長輩看過提醒之後，家屬的未讀數也跟著被清掉。家屬沿用原鍵名，
 * 避免既有裝置升版後未讀數整批復活。
 */

import * as SecureStore from "expo-secure-store";

type Audience = "guardian" | "elder";

const KEYS: Record<Audience, string> = {
  guardian: "kinsun_notifications_seen_at",
  elder: "kinsun_elder_notifications_seen_at",
};

export async function loadSeenAt(audience: Audience = "guardian"): Promise<number> {
  const raw = await SecureStore.getItemAsync(KEYS[audience]);
  const value = raw ? Number(raw) : 0;
  return Number.isFinite(value) ? value : 0;
}

export async function saveSeenAt(
  epochSeconds: number,
  audience: Audience = "guardian",
): Promise<void> {
  await SecureStore.setItemAsync(KEYS[audience], String(epochSeconds));
}
