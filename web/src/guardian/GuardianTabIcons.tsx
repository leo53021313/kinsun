/**
 * 家屬端五項導覽的圖示。
 *
 * ⚠️ 自己畫而不是裝圖示套件，理由同 `elder/TalkIcons.tsx`：AGENTS.md「除非有充分
 * 理由，否則不要新增第三方套件」，而這裡只需要五個形狀。
 *
 * ⚠️ 五個形狀刻意差異明顯（房子／圓餅／加號／鈴鐺／人像）。設計稿要求「每個圖示
 * 都有文字標籤」，圖示因此不是唯一線索，但**形狀相近的圖示在小尺寸下等於沒有**
 * ——老花的家屬掃一眼要分得出來。
 */

import type { ReactNode } from "react";

type IconProps = { size?: number };

function Svg(props: IconProps & { children: ReactNode }) {
  const { size = 26, children } = props;
  return (
    <svg
      aria-hidden
      focusable="false"
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={2.2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {children}
    </svg>
  );
}

export function HomeIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M3.5 10.5 12 3.5l8.5 7" />
      <path d="M5.5 9.5V20h13V9.5" />
      <path d="M10 20v-5.5h4V20" />
    </Svg>
  );
}

export function ReportIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 3.5v8.5h8.5" />
    </Svg>
  );
}

export function PlusIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M12 5v14M5 12h14" />
    </Svg>
  );
}

export function BellIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M6 10a6 6 0 0 1 12 0c0 4 1.5 5.5 2 6H4c.5-.5 2-2 2-6Z" />
      <path d="M10 19.5a2.2 2.2 0 0 0 4 0" />
    </Svg>
  );
}

export function PersonIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="8" r="3.8" />
      <path d="M4.5 20c1.2-3.6 4-5.5 7.5-5.5s6.3 1.9 7.5 5.5" />
    </Svg>
  );
}
