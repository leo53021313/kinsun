/**
 * 對講機麥克風鍵的手勢狀態機（純邏輯，不碰錄音 API）。
 *
 * 支援兩種說話方式（2026-07-25）：
 * - 按住說話：pressIn 開始聆聽 → 達長按門檻（longPress）→ pressOut 停止送出。
 * - 短按切換：pressIn 開始聆聽 → 未達門檻就 pressOut（keep，維持聆聽）→
 *   再按一下（pressIn）立即停止送出，該次按壓的 pressOut 不再動作。
 *
 * 用獨立狀態機而非 React state 判斷手勢：pressIn/pressOut 的間隔可能短於一次
 * 重繪，事件處理器讀 state 會拿到過期值——這正是先前「短按殘留聆聽中、二按
 * 洗掉音檔」bug 的根因。呼叫端只需依回傳的動作執行開錄／停錄。
 */

/** 呼叫端要執行的動作：開始錄音／停止送出／維持聆聽（顯示提示）／不動作。 */
export type TalkGestureAction = "start" | "stop" | "keep" | "none";

export function createTalkGesture() {
  // 是否正在聆聽（由本狀態機視角；錄音是否真的成功由呼叫端以 reset 回報失敗）。
  let recording = false;
  // 這次按壓是否已達長按門檻（按住說話模式：放開就送出）。
  let longPressed = false;
  // 這次按壓已在 pressIn 停止（短按切換的第二下），其 pressOut 應忽略。
  let stopHandledOnPressIn = false;

  return {
    pressIn(): TalkGestureAction {
      if (recording) {
        recording = false;
        stopHandledOnPressIn = true;
        return "stop";
      }
      // 每次新按壓都重置旗標：pressOut 可能被系統吃掉（如按壓中按鈕轉為
      // disabled），殘留旗標不可影響新一輪。
      longPressed = false;
      stopHandledOnPressIn = false;
      recording = true;
      return "start";
    },

    /** 由 Pressable onLongPress 觸發：標記本次按壓為「按住說話」模式。 */
    longPress(): void {
      longPressed = true;
    },

    pressOut(): TalkGestureAction {
      if (stopHandledOnPressIn) {
        stopHandledOnPressIn = false;
        return "none";
      }
      if (!recording) {
        return "none";
      }
      if (longPressed) {
        recording = false;
        return "stop";
      }
      return "keep";
    },

    /** 開錄失敗或流程異常時由呼叫端復位，回到待機。 */
    reset(): void {
      recording = false;
      longPressed = false;
      stopHandledOnPressIn = false;
    },
  };
}
