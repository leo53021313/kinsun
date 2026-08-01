/** vitest 的全域設定：把 @testing-library/jest-dom 的斷言（如 toBeInTheDocument）掛上。 */

import "@testing-library/jest-dom/vitest";

/**
 * jsdom 沒有音訊後端，`HTMLMediaElement` 的 `play`／`pause`／`load` 一律往虛擬
 * 主控台印一行「Not implemented」。那是必然的雜訊、不是問題——而雜訊會訓練人
 * 忽略測試輸出（同 eslint 那條 `no-irregular-whitespace` 放行全形空白的理由）。
 *
 * ⚠️ `play()` 額外補一個已解出的 Promise：jsdom 的版本回 `undefined`，而
 * `talk/playback.ts::play()` 依瀏覽器規格接 `.catch(...)`（真實瀏覽器一律回
 * Promise）。不補的話，任何真的走到播放的測試會拿到 `undefined.catch` 的
 * TypeError——那是環境差異，不是產品缺陷。
 *
 * 這裡刻意只讓它們閉嘴、不做任何行為模擬：本專案從不驗證「真的有聲音發出來」，
 * 播放行為一律以注入的假播放器驗證（見 `talk/playback.test.ts`）。
 */
Object.defineProperties(window.HTMLMediaElement.prototype, {
  play: { configurable: true, writable: true, value: () => Promise.resolve() },
  pause: { configurable: true, writable: true, value: () => undefined },
  load: { configurable: true, writable: true, value: () => undefined },
});
