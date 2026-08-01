/**
 * 長輩端用到的端點。
 *
 * ⚠️ 位置的鍵名是 `location` 而非本地型別的 `place`。線路契約由後端與
 * `POST /turns` 的參數定義——2026-07-28 的故障正是直接把本地欄位名送上去：
 * 後端讀不到 `location`，位置一列都沒寫進庫，金孫從此每次問地點都反問
 * 「您人在哪裡」，而那看起來完全像模型的行為問題。
 */

import type { AppNotification, ElderSession, TurnReply } from "kinsun-shared/types";

import { request } from "@/api";

export type ElderPlace = { place: string; latitude: number; longitude: number };

export function bindElderDevice(code: string): Promise<ElderSession> {
  return request("/api/v1/device-bindings", { method: "POST", body: JSON.stringify({ code }) });
}

/** 長輩帳密登入（✅ D-71 己-6）：帳號＝手機號碼；只管重登，未配對回 403。 */
export function loginElder(phone: string, password: string): Promise<ElderSession> {
  return request("/api/v1/elder-sessions", {
    method: "POST",
    body: JSON.stringify({ phone, password }),
  });
}

/** 登出＝撤銷這一個 token（✅ 庚-42：後端 `DELETE /sessions` 家屬與長輩 token 皆可）。
 *  失敗不擋本機登出，呼叫端自行忽略。 */
export function logoutSession(token: string): Promise<void> {
  return request("/api/v1/sessions", { method: "DELETE", token });
}

/**
 * 送出一輪（WebSocket 連不上時的降級路徑）。
 *
 * 位置走 query 參數：`/turns` 收的是裸音檔 body，它們在 body 裡沒有位置可放。
 * `null` ＝這輪沒有位置（未授權、室內收不到），不帶參數——不是「他不在任何地方」。
 */
export function postTurn(
  audio: ArrayBuffer,
  token: string,
  place: ElderPlace | null,
): Promise<TurnReply> {
  const query = place
    ? `?${new URLSearchParams({
        location: place.place,
        latitude: String(place.latitude),
        longitude: String(place.longitude),
      })}`
    : "";
  return request(`/api/v1/turns${query}`, {
    method: "POST",
    body: audio,
    // 後端的 ASR 靠 ffmpeg 嗅探容器，這個標頭只進 log；瀏覽器實際送的是
    // webm/opus 或 mp4/aac，兩種都吃得下。維持與 App 相同的值以免兩邊 log 不一致。
    headers: { "Content-Type": "audio/m4a" },
    token,
  });
}

/** 長輩讀自己的 App 內通知（用藥／回診提醒、主動關懷；X-01）。 */
export function listElderNotifications(token: string): Promise<AppNotification[]> {
  return request("/api/v1/elder-notifications", { token });
}
