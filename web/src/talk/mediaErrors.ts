/**
 * `getUserMedia` 失敗原因的白話分類（相機與麥克風共用）。
 *
 * ⚠️ **為什麼獨立成一個零依賴模組**：這段對應表原本只住在 `qrScanner.ts` 裡，
 * 而 Task 8 的麥克風探測需要一模一樣的判斷（同一支 API、同一組 `DOMException`
 * 名稱）。不可以從 `recorder.ts` 匯入 `qrScanner.ts`——後者在模組載入時就會執行
 * `prepareZXingModule(...)`、把 1 MB 的條碼 wasm 載入器綁進對講機這條路徑上，
 * 而對講機根本不掃碼。抄一份也不行：兩份對應表遲早各自漂移，而漂移的症狀是
 * 「同一個瀏覽器錯誤，相機講對了、麥克風講錯了」。
 *
 * 分類的用途只有一個：**決定要跟長輩說哪一句「下一步做什麼」**。「NotFoundError」
 * 對他沒有任何意義，「這台裝置沒有麥克風」才有。
 */

/**
 * - `"denied"`：使用者明確拒絕權限（或無法歸類的其他失敗原因，安全預設）。
 * - `"not-found"`：裝置根本沒有這個硬體（`NotFoundError`）——去開權限也沒用。
 * - `"in-use"`：硬體被別的程式佔用（`NotReadableError`）——手機上很常見。
 */
export type MediaAccessError = "denied" | "not-found" | "in-use";

/** 把瀏覽器擲出的 `DOMException.name` 對應到白話分類。 */
export function classifyMediaError(error: unknown): MediaAccessError {
  const name = error instanceof Error ? error.name : "";
  if (name === "NotFoundError" || name === "DevicesNotFoundError") {
    return "not-found";
  }
  if (name === "NotReadableError" || name === "TrackStartError") {
    return "in-use";
  }
  // 涵蓋 NotAllowedError（使用者拒絕）與其他無法歸類的成因；「denied」是最安全的
  // 預設——大多數不明成因也是引導使用者去檢查權限設定。
  return "denied";
}
