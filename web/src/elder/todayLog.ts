/**
 * 當天對話紀錄（W4 的資料層）。
 *
 * 只留當天，跟隨短期記憶的界線。逐字內容**只存在長輩自己的裝置**，家屬端 API
 * 不會讀取這個儲存區，也不會因此取得完整逐字對話。
 *
 * ⚠️ 值與規格對齊 `app/src/lib/todayLog.ts`，差別只在儲存後端：App 用
 * AsyncStorage（非同步），網頁用 `localStorage`（同步）。兩邊的 key 刻意相同
 * ——同一個瀏覽器不會同時跑兩端，而名字一致的話，日後要對照或搬遷不必再查。
 *
 * ⚠️ App 那份有一條序列化佇列，因為 AsyncStorage 是非同步的、三輪幾乎同時完成時
 * 會一起讀到同一份舊值、最後寫入者把前兩筆蓋掉。`localStorage` 是同步的，讀改寫
 * 之間不可能被插隊，所以這裡不需要那條佇列——照抄反而會讓人以為 web 也有那個
 * 競態。API 仍回 Promise，讓呼叫端兩端寫法一致。
 */

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

/** YYYY-MM-DD（本地時區）。跨日以裝置的自然日為準，不用 UTC。 */
function today(): string {
  const date = new Date();
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function parseStored(raw: string | null): Stored | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<Stored>;
    if (typeof parsed.day !== "string" || !Array.isArray(parsed.turns)) return null;
    return { day: parsed.day, turns: parsed.turns as TodayTurn[] };
  } catch {
    return null;
  }
}

/** 讀當天的對話。跨日自動視為空，不必等清除排程。 */
export async function loadToday(): Promise<TodayTurn[]> {
  try {
    const parsed = parseStored(localStorage.getItem(KEY));
    if (!parsed || parsed.day !== today()) return [];
    return parsed.turns;
  } catch {
    // 讀不到就當沒有；這是加分功能，不可讓它擋住對講機。
    // （無痕模式或 storage 配額用盡時 `localStorage` 會直接丟例外。）
    return [];
  }
}

/** 一輪回答播放完成時寫入。失敗不拋錯。 */
export async function appendTurn(turn: TodayTurn): Promise<void> {
  try {
    const day = today();
    const parsed = parseStored(localStorage.getItem(KEY));
    const turns = parsed?.day === day ? [...parsed.turns, turn] : [turn];
    const capped = turns.length > MAX_TURNS_PER_DAY ? turns.slice(-MAX_TURNS_PER_DAY) : turns;
    localStorage.setItem(KEY, JSON.stringify({ day, turns: capped } satisfies Stored));
  } catch {
    // 寫入失敗不影響對話。
  }
}

/** 登出或解除綁定時清空。 */
export async function clearToday(): Promise<void> {
  try {
    localStorage.removeItem(KEY);
  } catch {
    // 清除失敗不阻擋登出。
  }
}
