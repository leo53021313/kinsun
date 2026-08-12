/**
 * 對講機用的小圖示。
 *
 * ⚠️ 自己畫而不是裝圖示套件：AGENTS.md「除非有充分理由，否則不要新增第三方套件」，
 * 而這裡總共只需要六個形狀。App 那側用 Phosphor 是因為它整個 App 都在用。
 *
 * ⚠️ 為什麼不用 emoji（頁面其他地方用 🔔🎤）：狀態帶要做「顏色＋圖示＋文字」
 * 三重編碼，圖示必須跟著狀態換色——emoji 的顏色是字型決定的，`color` 改不動它。
 * 麥克風主鍵同理：說話時圖示要變成 #7A5E12。
 */

import type { AvatarState } from "./useTalk";

type IconProps = { size?: number; className?: string };

function Svg(props: IconProps & { children: React.ReactNode }) {
  const { size = 24, className, children } = props;
  return (
    <svg
      aria-hidden
      focusable="false"
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={2.4}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      {children}
    </svg>
  );
}

export function MicIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="9" y="2.5" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0" />
      <path d="M12 18v3.5" />
    </Svg>
  );
}

/** 五個狀態各給一個**形狀不同**的圖示——拿掉顏色仍分得出來，那是三重編碼的重點。 */
export function TalkStatusIcon(props: IconProps & { state: AvatarState }) {
  const { state, ...rest } = props;
  if (state === "listening") {
    // 波形：正在收音
    return (
      <Svg {...rest}>
        <path d="M4 10v4M8 6.5v11M12 3.5v17M16 6.5v11M20 10v4" />
      </Svg>
    );
  }
  if (state === "thinking") {
    // 三點：正在想
    return (
      <Svg {...rest}>
        <circle cx="5" cy="12" r="1.4" fill="currentColor" />
        <circle cx="12" cy="12" r="1.4" fill="currentColor" />
        <circle cx="19" cy="12" r="1.4" fill="currentColor" />
      </Svg>
    );
  }
  if (state === "speaking") {
    // 喇叭：正在說話
    return (
      <Svg {...rest}>
        <path d="M4 9.5v5h3.5L12 19V5L7.5 9.5H4Z" />
        <path d="M16 9a4.5 4.5 0 0 1 0 6" />
        <path d="M19 6.5a8.5 8.5 0 0 1 0 11" />
      </Svg>
    );
  }
  if (state === "error") {
    // 驚嘆三角：連線不穩
    return (
      <Svg {...rest}>
        <path d="M12 3.5 22 20H2L12 3.5Z" />
        <path d="M12 10v4" />
        <circle cx="12" cy="17" r="1.1" fill="currentColor" stroke="none" />
      </Svg>
    );
  }
  // idle：打勾圓圈，準備好了
  return (
    <Svg {...rest}>
      <circle cx="12" cy="12" r="9" />
      <path d="m8 12.5 2.8 2.8L16 9.5" />
    </Svg>
  );
}
