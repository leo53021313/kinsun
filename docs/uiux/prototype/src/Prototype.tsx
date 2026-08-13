import { useEffect, useRef, useState, type PointerEvent } from "react";
import {
  ArrowClockwise,
  CheckCircle,
  Microphone,
  SignOut,
  SpeakerHigh,
  Waveform,
  WifiSlash,
} from "@phosphor-icons/react";
import "@fontsource/noto-sans-tc/500.css";
import "@fontsource/noto-sans-tc/700.css";
import "@fontsource/noto-sans-tc/900.css";
import { MobileScroll } from "./mobile";

type ConversationState = "idle" | "listening" | "thinking" | "speaking" | "error";
type ListeningMode = "pressing" | "tap" | "hold";
type ResearchState =
  | "idle"
  | "listening-tap"
  | "listening-hold"
  | "thinking"
  | "speaking"
  | "error";
type StateContent = {
  label: string;
  description: string;
  action: string;
};
type InitialPrototypeView = {
  conversationState: ConversationState;
  listeningMode: ListeningMode | null;
  researchState: ResearchState | null;
};

const stateContent: Record<ConversationState, StateContent> = {
  idle: {
    label: "準備好了",
    description: "按住下面的麥克風說話，或按一下開始、說完再按一下。",
    action: "按住說話，或按一下開始",
  },
  listening: {
    label: "正在聽你說",
    description: "繼續按住，或現在放開改用短按模式。",
    action: "按住或放開",
  },
  thinking: {
    label: "想一下喔",
    description: "我正在整理你的話，馬上回答。",
    action: "正在想",
  },
  speaking: {
    label: "阿金正在說話",
    description: "今天天氣很舒服，我們慢慢聊。",
    action: "正在說",
  },
  error: {
    label: "連線不太穩",
    description: "剛才沒有送出去，重新連線就可以了。",
    action: "暫停使用",
  },
};

const listeningContent: Record<ListeningMode, StateContent> = {
  pressing: stateContent.listening,
  tap: {
    label: "正在聽你說",
    description: "金孫在聽，說完再按一下。",
    action: "說完再按一下",
  },
  hold: {
    label: "正在聽你說",
    description: "我正在聽，說完再放開按鈕。",
    action: "放開送出",
  },
};

function getInitialPrototypeView(): InitialPrototypeView {
  const fallback: InitialPrototypeView = {
    conversationState: "idle",
    listeningMode: null,
    researchState: null,
  };

  if (typeof window === "undefined") return fallback;

  const researchState = new URLSearchParams(window.location.search).get("research_state");
  if (researchState === "idle") {
    return { conversationState: "idle", listeningMode: null, researchState };
  }
  if (researchState === "listening-tap") {
    return { conversationState: "listening", listeningMode: "tap", researchState };
  }
  if (researchState === "listening-hold") {
    return { conversationState: "listening", listeningMode: "hold", researchState };
  }
  if (researchState === "thinking" || researchState === "speaking" || researchState === "error") {
    return { conversationState: researchState, listeningMode: null, researchState };
  }

  return fallback;
}

function StateIcon({ state }: { state: ConversationState }) {
  const iconProps = { size: 36, weight: "bold" as const, "aria-hidden": true };

  if (state === "listening") return <Waveform {...iconProps} />;
  if (state === "thinking") return <ArrowClockwise {...iconProps} className="spin-icon" />;
  if (state === "speaking") return <SpeakerHigh {...iconProps} />;
  if (state === "error") return <WifiSlash {...iconProps} />;
  return <CheckCircle {...iconProps} />;
}

function ActionIcon({ state }: { state: ConversationState }) {
  const iconProps = { size: 52, weight: "fill" as const, "aria-hidden": true };

  if (state === "listening") return <Waveform {...iconProps} />;
  if (state === "thinking") return <ArrowClockwise {...iconProps} className="spin-icon" />;
  if (state === "speaking") return <SpeakerHigh {...iconProps} />;
  if (state === "error") return <WifiSlash {...iconProps} />;
  return <Microphone {...iconProps} />;
}

export default function Prototype() {
  const initialView = useRef(getInitialPrototypeView()).current;
  const [conversationState, setConversationState] = useState<ConversationState>(
    initialView.conversationState,
  );
  const [listeningMode, setListeningMode] = useState<ListeningMode | null>(
    initialView.listeningMode,
  );
  const [logoutNotice, setLogoutNotice] = useState(false);
  const timersRef = useRef<number[]>([]);
  const longPressTimerRef = useRef<number | null>(null);
  const isRecordingRef = useRef(initialView.conversationState === "listening");
  const isPressingRef = useRef(false);
  const longPressedRef = useRef(initialView.listeningMode === "hold");
  const ignoreReleaseRef = useRef(false);
  const content =
    conversationState === "listening"
      ? listeningContent[listeningMode ?? "pressing"]
      : stateContent[conversationState];

  const clearLongPressTimer = () => {
    if (longPressTimerRef.current !== null) {
      window.clearTimeout(longPressTimerRef.current);
      longPressTimerRef.current = null;
    }
  };

  const clearTimers = () => {
    clearLongPressTimer();
    timersRef.current.forEach((timer) => window.clearTimeout(timer));
    timersRef.current = [];
  };

  useEffect(() => clearTimers, []);

  const resetVoiceGesture = () => {
    clearLongPressTimer();
    isRecordingRef.current = false;
    isPressingRef.current = false;
    longPressedRef.current = false;
    ignoreReleaseRef.current = false;
    setListeningMode(null);
  };

  const returnToIdle = (delay = 0) => {
    clearTimers();
    resetVoiceGesture();
    if (delay === 0) {
      setConversationState("idle");
      return;
    }

    timersRef.current.push(
      window.setTimeout(() => {
        setConversationState("idle");
      }, delay),
    );
  };

  const completeVoiceTurn = () => {
    clearTimers();
    resetVoiceGesture();
    setConversationState("thinking");
    timersRef.current.push(
      window.setTimeout(() => setConversationState("speaking"), 1100),
      window.setTimeout(() => setConversationState("idle"), 3400),
    );
  };

  /**
   * 與正式 App 的 talkGesture 對齊：
   * - 第一次短按放開後維持聆聽，第二次按下時送出。
   * - 按住超過 500ms 後，放開時送出。
   */
  const startListening = (event?: PointerEvent<HTMLButtonElement>) => {
    if (conversationState === "thinking" || conversationState === "speaking") return;

    isPressingRef.current = true;
    event?.currentTarget.setPointerCapture(event.pointerId);

    if (isRecordingRef.current) {
      if (listeningMode === "hold") {
        longPressedRef.current = true;
        return;
      }

      isRecordingRef.current = false;
      ignoreReleaseRef.current = true;
      completeVoiceTurn();
      return;
    }

    if (conversationState !== "idle") return;

    clearTimers();
    isRecordingRef.current = true;
    longPressedRef.current = false;
    ignoreReleaseRef.current = false;
    setListeningMode("pressing");
    setConversationState("listening");
    longPressTimerRef.current = window.setTimeout(() => {
      if (isRecordingRef.current && isPressingRef.current) {
        longPressedRef.current = true;
        setListeningMode("hold");
      }
    }, 500);
  };

  const stopListening = (event?: PointerEvent<HTMLButtonElement>) => {
    if (!isPressingRef.current) return;
    isPressingRef.current = false;
    clearLongPressTimer();
    if (event?.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }

    if (ignoreReleaseRef.current) {
      ignoreReleaseRef.current = false;
      return;
    }
    if (!isRecordingRef.current) return;

    if (longPressedRef.current) {
      isRecordingRef.current = false;
      completeVoiceTurn();
      return;
    }

    setListeningMode("tap");
  };

  const cancelListening = () => {
    if (!isPressingRef.current) return;
    returnToIdle();
  };

  const retryConnection = () => {
    clearTimers();
    setConversationState("thinking");
    returnToIdle(900);
  };

  const demonstrateLogout = () => {
    clearTimers();
    resetVoiceGesture();
    setConversationState("idle");
    setLogoutNotice(true);
    timersRef.current.push(window.setTimeout(() => setLogoutNotice(false), 2200));
  };

  return (
    <MobileScroll className="app-screen kinsun-app">
      <main
        className="talk-screen"
        data-state={conversationState}
        data-listening-mode={listeningMode ?? "none"}
        data-research-state={initialView.researchState ?? "none"}
        data-testid="talk-screen"
        aria-label="阿金陪伴對話 Prototype"
      >
        <header className="talk-header">
          <p className="eyebrow">陪伴對話</p>
          <button
            type="button"
            className="logout-button"
            onClick={demonstrateLogout}
            aria-label="登出 Prototype"
          >
            <SignOut size={25} weight="bold" aria-hidden />
            <span>登出</span>
          </button>
        </header>

        <section className="companion-section" aria-labelledby="companion-title">
          <h1 id="companion-title">阿金在這裡</h1>
          <img
            className="companion-art"
            src="/assets/akin-hero.png"
            alt="戴著圓眼鏡與橘色領巾的阿金，微笑陪伴使用者"
            data-testid="companion-art"
            draggable={false}
          />
        </section>

        <section
          className="status-band"
          data-testid="status-band"
          role={conversationState === "error" ? "alert" : "status"}
          aria-live={conversationState === "error" ? "assertive" : "polite"}
        >
          <span className="status-icon">
            <StateIcon state={conversationState} />
          </span>
          <strong data-testid="state-label">{content.label}</strong>
        </section>

        <p className="conversation-description">{content.description}</p>

        {conversationState === "error" ? (
          <section className="recovery-actions" aria-label="連線錯誤回復">
            <button type="button" className="retry-button" onClick={retryConnection} data-testid="retry-button">
              <ArrowClockwise size={27} weight="bold" aria-hidden />
              重新連線
            </button>
            <button type="button" className="secondary-button" onClick={() => returnToIdle()}>
              回到待機
            </button>
          </section>
        ) : (
          <section className="voice-action" aria-label="語音操作">
            <button
              type="button"
              className="microphone-button"
              data-testid="mic-button"
              data-scroll-drag="ignore"
              data-active={conversationState === "listening" ? "true" : "false"}
              disabled={conversationState === "thinking" || conversationState === "speaking"}
              aria-label={content.action}
              onPointerDown={startListening}
              onPointerUp={stopListening}
              onPointerCancel={cancelListening}
              onKeyDown={(event) => {
                if ((event.key === "Enter" || event.key === " ") && !event.repeat) {
                  event.preventDefault();
                  startListening();
                }
              }}
              onKeyUp={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  stopListening();
                }
              }}
            >
              <ActionIcon state={conversationState} />
            </button>
            <strong className="action-label" data-testid="action-label">
              {content.action}
            </strong>
          </section>
        )}

        <button
          type="button"
          className="error-demo-button"
          onClick={() => {
            clearTimers();
            resetVoiceGesture();
            setConversationState("error");
          }}
          data-testid="error-demo"
        >
          示範連線錯誤
        </button>

        {logoutNotice ? (
          <div className="prototype-toast" role="status" aria-live="polite">
            Prototype：已完成登出示範
          </div>
        ) : null}
      </main>
    </MobileScroll>
  );
}
