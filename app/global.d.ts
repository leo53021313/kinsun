import "react-native-svg";

// phosphor-react-native 3.0.6 會替 Svg 加上供 Web 使用的 CSS class；
// react-native-svg 15.12.1（Expo SDK 54 核准版本）的 SvgProps 尚未宣告此欄位。
// 套件官方 README 指示以 declaration merging 補齊，避免把第三方 src 型別排除檢查。
declare module "react-native-svg" {
  interface SvgProps {
    className?: string;
  }
}
