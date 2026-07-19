/** 麥克風圖示（對講機主鍵用）：白色線條，畫在橘色圓鈕上。用專案既有的 react-native-svg。 */

import Svg, { Path, Rect } from "react-native-svg";

export function MicIcon(props: { size?: number; color?: string }) {
  const size = props.size ?? 48;
  const color = props.color ?? "#FFFFFF";
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Rect x={9} y={2} width={6} height={11} rx={3} fill={color} />
      <Path d="M5 11v1a7 7 0 0 0 14 0v-1" stroke={color} strokeWidth={2} strokeLinecap="round" />
      <Path d="M12 19v3" stroke={color} strokeWidth={2} strokeLinecap="round" />
      <Path d="M8 22h8" stroke={color} strokeWidth={2} strokeLinecap="round" />
    </Svg>
  );
}
