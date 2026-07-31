/**
 * 通知已讀水位（沿用 App 的 ✅ D-12）：未讀數＝比水位新的通知數。
 *
 * ⚠️ 兩個角色分鍵。共用一支鍵會讓長輩看過提醒之後、家屬的未讀數也跟著被清掉，
 * 而雙欄同時在畫面上，這個 bug 會在展示的第一分鐘就被看到。
 *
 * ⚠️ **角色之外還要分「是誰」**（全分支審查發現的 Minor 2，2026-08-01）：P4 之前
 * 這支水位是**唯寫**的（沒有任何畫面讀它算未讀數），「同一個角色只有一個人」這個
 * 假設不承重；P4 Task 4 把 `notify/useNotificationFeed.ts` 的 `unread` 接上鈴鐺
 * 之後它開始承重了。失效情境（彩排一整天都會發生）：上午在這台瀏覽器測阿公
 * （提醒累積）→ 下午換阿嬤並開過提醒列表（水位被推到下午）→ 晚上換回阿公 →
 * **阿公整批舊提醒被算成已讀，鈴鐺顯示 0**。
 *
 * 修法是把鍵再多綁一層「現在登入的是誰」。⚠️ **識別碼刻意取 `display_name` 而不是
 * token**：token 每次重新配對／重新登入都會換一組，拿它當鍵等於每次登入都把水位
 * 洗掉、鈴鐺一律顯示全部未讀；而 web session 裡（`session/storage.ts::Session`）除了
 * token 就只有 `display_name` 這一個欄位可以認人——後端沒有把 `elder_id`／
 * `guardian_id` 放進登入回應。**已知限制**：兩位同名的長輩仍會共用同一支水位，
 * 這是接受的取捨（展示規模碰不到，且遠好過角色層級的全體共用）。
 *
 * ⚠️ 這裡直接讀 `session/storage.ts` 而不是要呼叫端多傳一個參數：`loadSeenAt`
 * ／`saveSeenAt` 的三個呼叫端（輪詢 hook＋兩支提醒列表）都必然在「有 session」
 * 的情況下才會執行，多傳一路只是把同一個值再抄一次、且抄錯了沒人會發現。
 */

import { loadSession, type Role } from "@/session/storage";

export type Audience = Role;

const KEYS: Record<Audience, string> = {
  guardian: "kinsun_web_seen_at_guardian",
  elder: "kinsun_web_seen_at_elder",
};

/**
 * 這個角色、這位使用者專屬的儲存鍵。
 *
 * 沒有 session 時後綴是空字串（一個獨立的「不知道是誰」水位）——那種情況下沒有
 * 任何畫面在算未讀數，落到哪一支水位都不影響使用者看到的東西。
 */
function storageKey(audience: Audience): string {
  return `${KEYS[audience]}:${loadSession(audience)?.display_name ?? ""}`;
}

export function loadSeenAt(audience: Audience): number {
  const raw = localStorage.getItem(storageKey(audience));
  const value = raw ? Number(raw) : 0;
  // 壞掉的值會讓 Number() 回 NaN，而 NaN 的任何比較都是 false——未讀數會永遠是 0。
  return Number.isFinite(value) ? value : 0;
}

export function saveSeenAt(epochSeconds: number, audience: Audience): void {
  localStorage.setItem(storageKey(audience), String(epochSeconds));
}

export function unreadCount(items: { created_at: number }[], seenAt: number): number {
  return items.filter((item) => item.created_at > seenAt).length;
}
