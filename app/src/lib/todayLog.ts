/** 當天對話紀錄（批次 4 的資料層，批次 3 先建立寫入點）。
 *
 * 只留當天，跟隨短期記憶的界線。逐字內容只存在長輩自己的裝置，家屬端 API
 * 不會讀取這個儲存區，也不會因此取得完整逐字對話。
 */

import AsyncStorage from "@react-native-async-storage/async-storage";

const KEY = "kinsun.todayLog.v1";
const MAX_TURNS_PER_DAY = 200;

export type TodayTurn = {
  /** 本地時間戳（毫秒）。 */
  at: number;
  /** 長輩說的話（ASR 結果）。 */
  said: string;
  /** 阿白的完整回答。 */
  reply: string;
  /** 回答的出處，健康類才有。 */
  source?: string;
};

type Stored = { day: string; turns: TodayTurn[] };

// 同一條 WebSocket 最多可同時處理三輪；若三輪幾乎同時完成，沒有這條序列化鏈就會
// 一起讀到同一份舊值，最後寫入者把前兩筆蓋掉。
let storageQueue: Promise<void> = Promise.resolve();

/** YYYY-MM-DD（本地時區）。跨日以裝置的自然日為準，不用 UTC。 */
function today(): string {
  const date = new Date();
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function enqueue(task: () => Promise<void>): Promise<void> {
  const next = storageQueue.then(task, task);
  storageQueue = next.catch(() => undefined);
  return storageQueue;
}

function parseStored(raw: string | null): Stored | null {
  if (!raw) return null;
  const parsed = JSON.parse(raw) as Partial<Stored>;
  if (typeof parsed.day !== "string" || !Array.isArray(parsed.turns)) return null;
  return { day: parsed.day, turns: parsed.turns as TodayTurn[] };
}

/** 讀當天的對話。跨日自動視為空，不必等清除排程。 */
export async function loadToday(): Promise<TodayTurn[]> {
  try {
    await storageQueue;
    const parsed = parseStored(await AsyncStorage.getItem(KEY));
    if (!parsed || parsed.day !== today()) return [];
    return parsed.turns;
  } catch {
    // 讀不到就當沒有；這是加分功能，不可讓它擋住對講機。
    return [];
  }
}

/** 一輪回答播放完成時寫入。失敗不拋錯。 */
export function appendTurn(turn: TodayTurn): Promise<void> {
  return enqueue(async () => {
    try {
      const day = today();
      const parsed = parseStored(await AsyncStorage.getItem(KEY));
      const turns = parsed?.day === day ? [...parsed.turns, turn] : [turn];
      const capped =
        turns.length > MAX_TURNS_PER_DAY ? turns.slice(-MAX_TURNS_PER_DAY) : turns;
      await AsyncStorage.setItem(KEY, JSON.stringify({ day, turns: capped } satisfies Stored));
    } catch {
      // 寫入失敗不影響對話。
    }
  });
}

/** 登出或解除綁定時清空。 */
export function clearToday(): Promise<void> {
  return enqueue(async () => {
    try {
      await AsyncStorage.removeItem(KEY);
    } catch {
      // 清除失敗不阻擋登出。
    }
  });
}
