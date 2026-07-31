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
 */

const SILENT_AUDIO_URL = "/demo/silent.wav";

let unlocked = false;

export function unlockAudio(player: { play: () => void; replace: (s: { uri: string }) => void }): void {
  if (unlocked) {
    return;
  }
  unlocked = true;
  player.replace({ uri: SILENT_AUDIO_URL });
  player.play();
}

/** 測試用：把解鎖狀態歸零。 */
export function resetAudioUnlockForTest(): void {
  unlocked = false;
}
