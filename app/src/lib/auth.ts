/** 登入狀態持久化：expo-secure-store 依身分各存一個 slot（內測可雙身分並存）。 */

import * as SecureStore from "expo-secure-store";

export type Role = "guardian" | "elder";

export type Session = {
  role: Role;
  token: string;
  display_name: string;
};

const SLOT_KEYS: Record<Role, string> = {
  guardian: "kinsun_session_guardian",
  elder: "kinsun_session_elder",
};
const ACTIVE_ROLE_KEY = "kinsun_active_role";
const LEGACY_KEY = "kinsun_session";

function parseSession(raw: string | null): Session | null {
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw) as Session;
  } catch {
    return null;
  }
}

/** 舊版單一 key 一次性搬遷到對應身分 slot；讀不懂就直接丟棄。 */
async function migrateLegacySession(): Promise<void> {
  const raw = await SecureStore.getItemAsync(LEGACY_KEY);
  if (raw === null) {
    return;
  }
  const legacy = parseSession(raw);
  if (legacy) {
    await SecureStore.setItemAsync(SLOT_KEYS[legacy.role], JSON.stringify(legacy));
    await SecureStore.setItemAsync(ACTIVE_ROLE_KEY, legacy.role);
  }
  await SecureStore.deleteItemAsync(LEGACY_KEY);
}

export async function saveSession(session: Session): Promise<void> {
  await SecureStore.setItemAsync(SLOT_KEYS[session.role], JSON.stringify(session));
  await SecureStore.setItemAsync(ACTIVE_ROLE_KEY, session.role);
}

export async function loadSessionForRole(role: Role): Promise<Session | null> {
  return parseSession(await SecureStore.getItemAsync(SLOT_KEYS[role]));
}

export async function loadActiveSession(): Promise<Session | null> {
  await migrateLegacySession();
  const active = await SecureStore.getItemAsync(ACTIVE_ROLE_KEY);
  if (active !== "guardian" && active !== "elder") {
    return null;
  }
  return loadSessionForRole(active);
}

export async function setActiveRole(role: Role): Promise<void> {
  await SecureStore.setItemAsync(ACTIVE_ROLE_KEY, role);
}

/** 只清指定身分的登入；另一身分（若有）不受影響。 */
export async function clearSession(role: Role): Promise<void> {
  await SecureStore.deleteItemAsync(SLOT_KEYS[role]);
  const active = await SecureStore.getItemAsync(ACTIVE_ROLE_KEY);
  if (active === role) {
    await SecureStore.deleteItemAsync(ACTIVE_ROLE_KEY);
  }
}
