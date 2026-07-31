/**
 * 通知橫幅的作業系統風格。
 *
 * 依 UA 給一個合理的預設，但**一定要能手動切換**——展示時觀眾會想看兩種，
 * 而且投影用的筆電只有一種 UA。
 */

// ⚠️ 型別**不重新宣告**：`PhoneOs` 的出處是 PhoneFrame（P1 Task 9），這裡只轉出。
// 各自宣告一份的話，兩邊哪天分岔了 TypeScript 也不會說話——它們結構相同。
export type { PhoneOs } from "@/stage/PhoneFrame";

/**
 * Apple 系（含 macOS）給 iOS 風，其餘給 Android 風。
 *
 * macOS 也算 iOS 風不是偷懶：用 Mac 展示時，觀眾看到的應該是 Apple 的視覺語彙，
 * 那比「因為它不是手機所以給 Material」更符合直覺。
 */
export function detectOs(userAgent: string): "ios" | "android" {
  return /iPhone|iPad|iPod|Macintosh/i.test(userAgent) ? "ios" : "android";
}
