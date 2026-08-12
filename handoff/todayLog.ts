/** 當天對話紀錄（批次 4 的資料層，批次 3 先建立寫入點）。
 *
 * 只留當天，跟隨短期記憶的界線：
 *   短期記憶 = 當次 session 的逐字內容 → 這裡存的就是它
 *   長期記憶（Mem0）= 萃取後的事實，不是逐字稿 → 不在這裡
 *
 * 資料不離開長輩的手機，因此不牴觸 api.ts 的「家屬可看摘要、不開放逐字對話」。
 */

import AsyncStorage from "@react-native-async-storage/async-storage";

const KEY = "kinsun.todayLog.v1";

export type TodayTurn = {
  /** 本地時間戳（毫秒） */
  at: number;
  /** 長輩說的話（ASR 結果） */
  said: string;
  /** 阿白的回答（完整文字，不是分段） */
  reply: string;
  /** 回答的出處，健康類才有 */
  source?: string;
};

type Stored = { day: string; turns: TodayTurn[] };

/** YYYY-MM-DD（本地時區）。跨日以裝置的自然日為準，不用 UTC。 */
function today(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/** 讀當天的對話。跨日自動視為空，不必等清除排程。 */
export async function loadToday(): Promise<TodayTurn[]> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Stored;
    if (parsed.day !== today()) return [];
    return parsed.turns ?? [];
  } catch {
    // 讀不到就當沒有——這是加分功能，不可讓它擋住對講機
    return [];
  }
}

/** 一輪對話結束時寫入。失敗不拋錯。 */
export async function appendTurn(turn: TodayTurn): Promise<void> {
  try {
    const day = today();
    const raw = await AsyncStorage.getItem(KEY);
    const parsed = raw ? (JSON.parse(raw) as Stored) : null;
    const turns = parsed && parsed.day === day ? parsed.turns : [];
    turns.push(turn);
    // 上限保護：一天超過 200 輪只留最近的，避免無限長大
    const capped = turns.length > 200 ? turns.slice(-200) : turns;
    await AsyncStorage.setItem(KEY, JSON.stringify({ day, turns: capped } satisfies Stored));
  } catch {
    // 寫入失敗就算了，不影響對話
  }
}

/** 登出或解除綁定時清空。 */
export async function clearToday(): Promise<void> {
  try {
    await AsyncStorage.removeItem(KEY);
  } catch {
    // ignore
  }
}
