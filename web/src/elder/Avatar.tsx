/**
 * 虛擬形象預留區：以表情符號＋狀態樣式呈現；日後換 Rive／Live2D 不動版面。
 *
 * ⚠️ 表情符號對讀螢幕軟體幾乎沒有資訊量（各家唸法不一，也可能整個略過），所以
 * 一定要有 `aria-label`——那是視障長輩唯一知道「金孫現在在聽還是在想」的方式。
 * 文案走 `strings.ts`，元件裡不出現裸中文字串。
 */

import { strings } from "@/strings";

import type { AvatarState } from "./useTalk";

const FACES: Record<AvatarState, string> = {
  idle: "😊",
  listening: "👂",
  thinking: "🤔",
  speaking: "😄",
};

export function Avatar(props: { state: AvatarState }) {
  return (
    <div
      role="img"
      aria-label={strings.talk.avatar[props.state]}
      className={`flex size-40 items-center justify-center rounded-full border-4 bg-surface text-7xl ${
        props.state === "listening" ? "border-primary" : "border-line"
      }`}
    >
      {FACES[props.state]}
    </div>
  );
}
