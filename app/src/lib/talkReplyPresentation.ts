const SUMMARY_LENGTH = 12;
const MIN_SPEECH_CHUNK_CHARS = 8;
const SPEECH_BOUNDARY = /[。！？!?\n]/u;

export type ReplyDraftContent = { reply: string; finalReceived: boolean };

/**
 * 套用 WS 回覆內容訊框。
 *
 * `reply.text` 依協定已是完整回答；後續 `chunk.text` 只是該段音訊的對嘴／字幕素材，
 * 不得再串進完整回答，否則回話卡與 todayLog 會重複後半段。
 */
export function applyReplyContentFrame(
  current: ReplyDraftContent,
  frame:
    | { type: "reply"; text: string; chunk_count: number }
    | { type: "chunk"; text: string; is_last: boolean },
): ReplyDraftContent {
  if (frame.type === "reply") {
    return { reply: frame.text, finalReceived: frame.chunk_count <= 1 };
  }
  return {
    reply: current.reply,
    finalReceived: current.finalReceived || frame.is_last,
  };
}

/**
 * WS 第一個 `reply` 的文字是全文，但同訊框音檔在 `chunk_count > 1` 時只唸第一段。
 * 這裡鏡射後端 `speech/chunking.py` 的第一段合併規則，讓 viseme 吃到真正正在播放的字。
 */
export function firstReplyAudioText(reply: string, chunkCount: number): string {
  const text = reply.trim();
  if (!text || chunkCount <= 1) return text;

  const characters = Array.from(text);
  let buffer = "";
  for (let index = 0; index < characters.length; index += 1) {
    buffer += characters[index];
    if (!SPEECH_BOUNDARY.test(characters[index])) continue;
    while (
      index + 1 < characters.length &&
      SPEECH_BOUNDARY.test(characters[index + 1])
    ) {
      index += 1;
      buffer += characters[index];
    }
    if (Array.from(buffer.trim()).length >= MIN_SPEECH_CHUNK_CHARS) return buffer;
  }
  return text;
}

/** 收合卡只顯示回答前 12 個 Unicode 字元，不會把 surrogate pair 切成半個字。 */
export function collapsedReplySummary(prefix: string, reply: string): string {
  const text = reply.trim();
  if (!text) return prefix;
  return `${prefix}${Array.from(text).slice(0, SUMMARY_LENGTH).join("")}…`;
}

export function shouldScrollTalkContent(fontScale: number): boolean {
  return fontScale >= 1.5;
}

/** 空白的 chunk 是協定終止訊框，不是要播放的音訊。 */
export function hasPlayableReplyAudio(frame: {
  type: string;
  text: string;
  audio_url: string;
}): boolean {
  return Boolean(frame.audio_url && !(frame.type === "chunk" && !frame.text));
}
