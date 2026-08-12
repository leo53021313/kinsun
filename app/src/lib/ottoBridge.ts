/**
 * 阿白 renderer bridge 的 App 端入口。
 *
 * 實作已於 2026-08-09 搬到 `shared/ottoBridge.ts`（✅ D-51 三端共用包）——網頁版
 * 載入同一份 `renderer.html`，協定分成兩份會各自演化，而對不上時的症狀是「阿白
 * 不動」，不是編譯錯誤。這裡保留為轉出，既有的 `@/lib/ottoBridge` 匯入全部不必改。
 */

export {
  OTTO_BRIDGE_VERSION,
  createOttoSyncCommand,
  parseOttoRendererEvent,
  type OttoRendererEvent,
  type OttoSpeechCue,
  type OttoSyncCommand,
  type OttoVisualState,
} from "kinsun-shared/ottoBridge";
