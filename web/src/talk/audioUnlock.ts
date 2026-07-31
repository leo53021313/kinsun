/**
 * iOS Safari 音訊解鎖（spec §12 R-1）。
 *
 * ⚠️ **為什麼需要它**：iOS Safari 不允許在沒有使用者手勢的情況下播放音訊，而金孫
 * 的回覆是在 WebSocket 訊框抵達時才播——那已經脫離「按下麥克風」的手勢鏈。不做
 * 這件事的症狀是「iPhone 上只看得到字、聽不到聲音，桌機一切正常」，而那種只在
 * 特定裝置出現的症狀查起來非常久。
 *
 * 做法：在第一次使用者互動時播一段極短的無聲音檔，之後這個播放器就解鎖了。
 *
 * ⚠️ 無聲音檔必須是**同源的靜態檔**，不可用 `data:` URI——CSP 的
 * `media-src 'self' https: blob:` 不含 `data:`，用 data URI 會被自家政策擋掉，
 * 而症狀正好也是「iPhone 上沒有聲音」，兩者混在一起會查到懷疑人生。
 *
 * ⚠️ **不要在「開始錄音」的同一個手勢裡呼叫這個函式**：`docs/dev/17_前端資訊
 * 架構.md` 記載 2026-07-18 的一次真實故障——App 端當初在手勢裡先播提示音再
 * 開始錄音，WebKit 的音訊工作階段被播放搶走，導致 iPhone 錄到的音檔全部
 * ≤0.72 秒且近無聲，修法是「開錄的那一刻不要播任何東西」。本模組的無聲檔
 * 播放與麥克風開錄若被安排在同一次使用者手勢裡（例如都掛在同一個
 * `pointerdown`），有重演這個故障的風險，且**無法在無頭測試環境判定**——
 * 見任務報告的人工驗收清單。掛在哪個手勢由後續任務決定；若真的重演，修法
 * 是把 `unlockAudio` 移到更早、與開錄不同的手勢，而不是動麥克風鍵本身。
 */

import { UNLOCK_AUDIO_URI } from "./playback";

let unlocked = false;

export function unlockAudio(player: { play: () => void; replace: (s: { uri: string }) => void }): void {
  if (unlocked) {
    return;
  }
  // ⚠️ 先上鎖再播放：`player.play()` 是 `PlayerLike` 的同步介面（不回傳
  // promise），本函式**看不到**底層播放到底成不成功——`WebPlayer.play()`
  // 內部把 `HTMLMediaElement.play()` 的 rejection 吞掉（見 playback.ts），
  // 就算改成「拿到成功訊號才上鎖」也等不到任何訊號可用。這代表若真的解鎖
  // 失敗（例如未來改成在非手勢時機呼叫、被 iOS 擋下），旗標仍會維持
  // `true`、之後不會再嘗試。目前的呼叫時機（使用者手勢的同步呼叫堆疊內）
  // 下這不是問題；若日後改動呼叫時機，須連同這裡的假設一起重新檢視。
  unlocked = true;
  player.replace({ uri: UNLOCK_AUDIO_URI });
  player.play();
}

/** 測試用：把解鎖狀態歸零。 */
export function resetAudioUnlockForTest(): void {
  unlocked = false;
}
