/** 登入狀態持久化：expo-secure-store 存 {role, token, display_name}。 */

import * as SecureStore from "expo-secure-store";

export type Session = {
  role: "guardian" | "elder";
  token: string;
  display_name: string;
};

const KEY = "kinsun_session";

export async function saveSession(session: Session): Promise<void> {
  await SecureStore.setItemAsync(KEY, JSON.stringify(session));
}

export async function loadSession(): Promise<Session | null> {
  const raw = await SecureStore.getItemAsync(KEY);
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw) as Session;
  } catch {
    return null;
  }
}

export async function clearSession(): Promise<void> {
  await SecureStore.deleteItemAsync(KEY);
}
