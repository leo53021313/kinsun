/**
 * 通知已讀水位（沿用 App 的 ✅ D-12）：未讀數＝比水位新的通知數。
 *
 * ⚠️ 兩個角色分鍵。共用一支鍵會讓長輩看過提醒之後、家屬的未讀數也跟著被清掉，
 * 而雙欄同時在畫面上，這個 bug 會在展示的第一分鐘就被看到。
 */

export type Audience = "guardian" | "elder";

const KEYS: Record<Audience, string> = {
  guardian: "kinsun_web_seen_at_guardian",
  elder: "kinsun_web_seen_at_elder",
};

export function loadSeenAt(audience: Audience): number {
  const raw = localStorage.getItem(KEYS[audience]);
  const value = raw ? Number(raw) : 0;
  // 壞掉的值會讓 Number() 回 NaN，而 NaN 的任何比較都是 false——未讀數會永遠是 0。
  return Number.isFinite(value) ? value : 0;
}

export function saveSeenAt(epochSeconds: number, audience: Audience): void {
  localStorage.setItem(KEYS[audience], String(epochSeconds));
}

export function unreadCount(items: { created_at: number }[], seenAt: number): number {
  return items.filter((item) => item.created_at > seenAt).length;
}
