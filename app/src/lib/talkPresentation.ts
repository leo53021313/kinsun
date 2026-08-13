import { strings } from "@/lib/strings";

export type TalkVisualState = "idle" | "listening" | "thinking" | "speaking" | "error";
export type ListeningMode = "pressing" | "tap" | "hold";
export type TalkSocketPlaybackKind = "ack" | "reply";

export type TalkPresentation = {
  statusLabel: string;
  actionLabel: string;
};

/**
 * WebSocket 語音播完後的畫面狀態。
 *
 * 安撫語音只代表「已收到、正在處理」，播完不能顯示成可再次說話；正式回覆若還有
 * 分段，則由續播流程維持 speaking，不在這裡搶著改狀態。
 */
export function getTalkSocketPlaybackCompletionState(
  kind: TalkSocketPlaybackKind,
  hasPendingReplyChunks: boolean,
): TalkVisualState | null {
  if (kind === "ack") {
    return "thinking";
  }
  return hasPendingReplyChunks ? null : "idle";
}

/**
 * WebSocket 訊框抵達但沒有可播放語音時的狀態。
 *
 * 後端允許 TTS 降級成純文字回覆；此時不會進播放佇列，所以必須在訊框抵達時直接
 * 收尾。帶語音的訊框則交給播放完成事件決定狀態。
 */
export function getTalkSocketFrameArrivalState(
  kind: TalkSocketPlaybackKind,
  hasAudio: boolean,
): TalkVisualState | null {
  if (hasAudio) {
    return null;
  }
  return kind === "ack" ? "thinking" : "idle";
}

/**
 * 對講機畫面文案只反映目前狀態；錄音是否開始、何時送出仍由 talkGesture 狀態機決定。
 */
export function getTalkPresentation(
  state: TalkVisualState,
  listeningMode: ListeningMode | null,
): TalkPresentation {
  if (state === "listening") {
    const actionLabel =
      listeningMode === "tap"
        ? strings.talk.actions.tapToSend
        : listeningMode === "hold"
          ? strings.talk.actions.releaseToSend
          : strings.talk.actions.listening;
    return {
      statusLabel: strings.talk.status.listening,
      actionLabel,
    };
  }
  if (state === "thinking") {
    return {
      statusLabel: strings.talk.status.thinking,
      actionLabel: strings.talk.actions.thinking,
    };
  }
  if (state === "speaking") {
    return {
      statusLabel: strings.talk.status.speaking,
      actionLabel: strings.talk.actions.speaking,
    };
  }
  if (state === "error") {
    return {
      statusLabel: strings.talk.status.error,
      actionLabel: strings.talk.actions.retry,
    };
  }
  return {
    statusLabel: strings.talk.status.idle,
    actionLabel: strings.talk.actions.start,
  };
}
