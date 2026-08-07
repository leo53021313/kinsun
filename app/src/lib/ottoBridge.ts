import type { TalkVisualState } from "@/lib/talkPresentation";

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
  state: TalkVisualState;
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
  state: TalkVisualState,
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
