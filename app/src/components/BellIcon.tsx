/** 鈴鐺圖示（對講機頁的提醒入口）：線條與 MicIcon 同粗細，畫在淺色圓底上。 */

import Svg, { Path } from "react-native-svg";

export function BellIcon(props: { size?: number; color?: string }) {
  const size = props.size ?? 28;
  const color = props.color ?? "#3A3A3A";
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Path
        d="M6 9a6 6 0 1 1 12 0c0 3.5.8 5.2 1.6 6.2.4.5 0 1.3-.7 1.3H5.1c-.7 0-1.1-.8-.7-1.3C5.2 14.2 6 12.5 6 9Z"
        stroke={color}
        strokeWidth={2}
        strokeLinejoin="round"
      />
      <Path d="M10 20a2 2 0 0 0 4 0" stroke={color} strokeWidth={2} strokeLinecap="round" />
    </Svg>
  );
}
