/**
 * 登入狀態持久化：依角色各存一個鍵，左右兩欄互不干擾。
 *
 * ⚠️ 用 localStorage 而非 App 的 expo-secure-store——後者在網頁的實作是
 * `export default {}`（空物件），沒有可搬的路。這是刻意接受的降級：本前端不
 * 服務真實長輩，存的是內部測試帳號的 token，風險與 admin 金鑰存 localStorage
 * 的既有例外同級（docs/dev/12 §7）。
 */

export type Role = "elder" | "guardian";

export type Session = {
  role: Role;
  token: string;
  display_name: string;
};

const KEYS: Record<Role, string> = {
  elder: "kinsun_web_session_elder",
  guardian: "kinsun_web_session_guardian",
};

export function loadSession(role: Role): Session | null {
  const raw = localStorage.getItem(KEYS[role]);
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw) as Session;
  } catch {
    // 存的內容壞掉（手動改過、版本不合）就當作沒登入。讓它擲出去的話，
    // 整個舞台會在掛載時白畫面，而使用者連「清除資料」的按鈕都看不到。
    return null;
  }
}

export function saveSession(session: Session): void {
  localStorage.setItem(KEYS[session.role], JSON.stringify(session));
}

export function clearSession(role: Role): void {
  localStorage.removeItem(KEYS[role]);
}
