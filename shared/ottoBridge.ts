/**
 * 阿白 renderer 的版本化 bridge 協定（三端共用，✅ D-51）。
 *
 * 2026-08-09 由 `app/src/lib/ottoBridge.ts` 搬來：網頁版 W3 要載入同一份
 * `renderer.html`，協定若在 web 那側另寫一份，兩份的欄位裁切與版本檢查就會各自
 * 演化——而 renderer 只有一份，對不上時的症狀是「阿白不動」而不是編譯錯誤。
 *
 * ⚠️ 這裡刻意宣告自己的 `OttoVisualState`，不從 app 的 `talkPresentation` 匯入：
 * 那支是接手指示第 11 條點名不准動的狀態機檔案，而 `shared/` 也不該反向依賴任何
 * 一端。兩者是同一組五個名稱，app 端以型別相容性（`ottoBridge.test.ts` 有一條
 * 編譯期斷言）確保不會漂。
 */

/** 對講機的五個視覺狀態。名稱與時機完全沿用既有狀態機，此處只是協定的一份宣告。 */
export type OttoVisualState = "idle" | "listening" | "thinking" | "speaking" | "error";

export const OTTO_BRIDGE_VERSION = 1 as const;

export type OttoSpeechCue = {
  /** 每一段實際播放都要有不同 key，確保同文案重播時仍重新對嘴。 */
  key: string;
  text: string;
  durationMs: number;
  emotion?: string | null;
};

export type OttoSyncCommand = {
  version: typeof OTTO_BRIDGE_VERSION;
  type: "sync";
  sequence: number;
  state: OttoVisualState;
  text?: string;
  durationMs?: number;
  emotion?: string;
};

export type OttoRendererEvent = {
  version: typeof OTTO_BRIDGE_VERSION;
  type: "ready" | "invalid-message";
};

export function createOttoSyncCommand(
  sequence: number,
  state: OttoVisualState,
  speechCue: OttoSpeechCue | null,
): OttoSyncCommand {
  const command: OttoSyncCommand = {
    version: OTTO_BRIDGE_VERSION,
    type: "sync",
    sequence,
    state,
  };
  if (state !== "speaking" || !speechCue) {
    return command;
  }
  command.text = speechCue.text.slice(0, 500);
  command.durationMs = Number.isFinite(speechCue.durationMs)
    ? Math.min(120_000, Math.max(0, Math.round(speechCue.durationMs)))
    : 0;
  if (speechCue.emotion) {
    command.emotion = speechCue.emotion;
  }
  return command;
}

export function parseOttoRendererEvent(data: string): OttoRendererEvent | null {
  let value: unknown;
  try {
    value = JSON.parse(data);
  } catch {
    return null;
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  const event = value as Record<string, unknown>;
  if (
    event.version !== OTTO_BRIDGE_VERSION ||
    (event.type !== "ready" && event.type !== "invalid-message")
  ) {
    return null;
  }
  return { version: OTTO_BRIDGE_VERSION, type: event.type };
}
