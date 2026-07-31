/**
 * 跨欄事件匯流排。
 *
 * ⚠️ 為什麼需要它：輪詢負責「後端主動產生的東西」（危急警報、排程提醒），但家屬
 * 剛按下的那個新增排程，長輩端要等最多兩秒才看得到——而展示時那兩秒剛好落在
 * 「你看，左邊出現了」這句話的中間。兩欄在同一個 JS 環境裡，直接通知一聲就好。
 *
 * 刻意做得極小：它不搬運資料，只說「有事發生了，你自己去拉」。搬資料的話兩欄
 * 就得共用型別與快取，而那正是把兩個獨立的畫面黏成一團的第一步。
 */

import { useEffect, useState } from "react";

export type StageEvent = "guardian-wrote" | "elder-talked";

const listeners = new Map<StageEvent, Set<() => void>>();

export function emitStageEvent(event: StageEvent): void {
  listeners.get(event)?.forEach((listener) => listener());
}

/**
 * 回一個每次事件都會變的計數；直接餵給 `useNotificationFeed` 的 `reloadSignal`。
 *
 * ⚠️ **`set.delete(listener)` 這行變異驗證時發現是等價變異（實測，非推測）**：
 * `bus.test.ts`「卸載後不再更新」那條測試，把這行清空成空函式（不移除訂閱者）
 * 之後 4 條測試仍然全線通過——React 19 對「已卸載元件呼叫 setState」既不拋錯也
 * 不印 `console.error`（已用獨立探測測試證實：同一支 hook 卸載後呼叫
 * `emitStageEvent`，`console.error` 呼叫次數為 0），而 `renderHook` 的
 * `result.current` 只反映最後一次真正 commit 的 render，卸載後的元件不會再
 * commit，因此就算殘留的監聽器仍被呼叫、`setTick` 仍被執行，從這支測試的黑盒
 * 角度完全看不出差別。這行仍然有單獨承重的路徑——長時間執行的分頁反覆掛載／
 * 卸載使用這個 hook 的元件時，不清掉的話 `listeners` 這個模組層級 Map 會無界
 * 累積死掉的閉包（真實的記憶體洩漏），只是目前的測試證明不了這件事；要證明
 * 需要額外對外洩漏 `listeners` 的內部狀態（如新增一個測試專用的計數匯出），
 * 但那會讓這個刻意做得極小的模組多一個沒有真實呼叫端的介面，故未追加。
 */
export function useStageEvent(event: StageEvent): number {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const listener = () => setTick((value) => value + 1);
    const set = listeners.get(event) ?? new Set();
    set.add(listener);
    listeners.set(event, set);
    return () => {
      set.delete(listener);
    };
  }, [event]);
  return tick;
}
