/**
 * 兩欄的 session context。
 *
 * ⚠️ 獨立成一個模組而不是放在 `StagePage` 裡：兩欄的畫面元件都要用到它，而
 * `StagePage` 又要用那些畫面元件——放在一起就是循環匯入。打包工具通常忍得住，
 * 但測試環境會在某些載入順序下拿到 undefined，那種錯誤查起來非常久。
 */

import { createSessionContext } from "./createSessionContext";

export const ElderSession = createSessionContext("elder");
export const GuardianSession = createSessionContext("guardian");
