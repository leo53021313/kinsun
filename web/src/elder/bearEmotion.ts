/**
 * 阿白的回應情緒政策（web 端）。
 *
 * ⚠️ 與角色舞台分成兩個檔案，不是為了整齊：`BearStage.tsx` 匯出元件以外的東西會讓
 * React Fast Refresh 對整個模組失效（改一行樣式就整頁重載，長輩端的對講機狀態跟著
 * 歸零）。App 端把這些放在 `BearStage.tsx` 裡是因為那邊的 lint 設定不同，不是本檔
 * 該跟隨的形狀。
 */

import type { OttoSpeechCue } from "kinsun-shared/ottoBridge";

import type { AvatarState } from "./useTalk";

/**
 * 阿白不會對長輩表現出來的情緒。
 *
 * ⚠️ **CRITICAL（接手指示第 10 條）**：阿白可以同理長輩的不舒服，但不能對長輩生氣、
 * 不耐、嫌惡、猜忌或驚慌。這份清單與 `shared/otto-pet-core/sentiment.js` 的
 * `BLOCKED_EMOTIONS`、App 端 `theme.ts` 的 `emotionPolicy.blocked` 是**同一份**
 * ——三處漂掉不會有任何症狀，直到長輩罵阿白的那一刻。web 這份由
 * `BearStage.test.tsx` 的一致性測試守著（App 那份由 `test-otto-runtime.mjs` 守）。
 *
 * ⚠️ renderer 內的 `PET.sanitizeEmotion` 才是執行期的真防線——本地關鍵詞比對也會挑到
 * angry（「生氣」「可惡」「討厭」等詞），那條路徑不經過本檔。這一層是**送出去之前**
 * 就先擋掉的深度防禦，與 App 端同形。
 */
export const BLOCKED_EMOTIONS = Object.freeze([
  // 對長輩本人的負面情緒：阿白不能對長輩不耐煩
  "angry",
  "furious",
  "annoyed",
  "disgusted",
  "jealous",
  "suspicious",
  "bored",
  "sulking",
  // 會嚇到人：長輩說胸口悶時要沉穩，慌張交給家屬端危急通知
  "panic",
  "shocked",
  "scared",
]);

/** 黑名單情緒一律回 `null`，讓協定層不帶 `emotion` 欄位（renderer 於是自己判讀文字）。 */
export function sanitizeEmotion(emotion: string | null | undefined): string | null {
  if (!emotion) return null;
  return BLOCKED_EMOTIONS.includes(emotion) ? null : emotion;
}

/**
 * 回應情緒只在 speaking 態併進 cue；其餘狀態下它沒有意義（協定層也會忽略）。
 *
 * ⚠️ **prop 沒給時要保留 cue 自己帶的**（D-82，2026-08-16）：表情現在由後端隨回覆
 * 送來、跟著那一則語音走（見 `useTalk`），而 `emotion` prop 是給呈現層臨時覆寫用的、
 * 平時沒有人傳。若拿 `undefined` 無條件覆蓋，後端指定的表情會在最後一步被抹掉——而
 * 症狀是「表情又變回本地判讀」，不會有任何錯誤。
 *
 * 兩條路徑都過黑名單：不論表情從哪裡來，阿白都不對長輩生氣。
 */
export function bearSpeechCue(
  state: AvatarState,
  emotion: string | null | undefined,
  speechCue: OttoSpeechCue | null,
): OttoSpeechCue | null {
  if (state !== "speaking" || !speechCue) return speechCue;
  return { ...speechCue, emotion: sanitizeEmotion(emotion ?? speechCue.emotion) };
}
