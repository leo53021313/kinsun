/** 設計常數：長輩端適老化（大字、高對比、大目標），家屬端沿用同一套色。 */

export const colors = {
  background: "#FFF9F0",
  surface: "#FFFFFF",
  primary: "#C2410C", // 溫暖磚橘：高對比主行動色
  primaryPressed: "#9A3412",
  text: "#1C1917",
  textSoft: "#57534E",
  border: "#E7E5E4",
  danger: "#B91C1C",
  success: "#15803D",
};

/** 對講機核准視覺：只套用於長輩陪伴對話，不改動家屬端既有配色。 */
export const talkColors = {
  ink: "#171D2A",
  paper: "#FFFDF8",
  blue: "#76BDF0",
  yellow: "#FFC928",
  coral: "#FF6A33",
  coralPressed: "#E84D1E",
  thinking: "#F7D984",
  speaking: "#A6D7B9",
  error: "#FFD2C7",
  errorText: "#7B1E1A",
  shadow: "rgba(23, 29, 42, 0.16)",
};

export const elder = {
  /** 長輩端最小字級 */
  fontMin: 22,
  fontBig: 30,
  fontHuge: 40,
};

export const spacing = { xs: 4, s: 8, m: 16, l: 24, xl: 40 };
