/** 設計常數：兩端共用同一套色票；長輩端只在字級、觸控與版面節奏上放大。
 *
 * 2026-08 改版：長輩端原本的粗墨線 × 硬邊位移陰影 × 珊瑚橘方案已作廢，
 * talkColors 整組移除。引用 talkColors 的檔案會編譯失敗——這是刻意的，
 * 順著錯誤清單改比自己找漏網的可靠。
 */

export const colors = {
  background: "#F5F5FD",        // 淡紫灰，家屬端頁面底
  backgroundWarmTop: "#FFF9EC", // 長輩端漸層起點（→ background）
  surface: "#FFFFFF",
  primary: "#4D50A2",
  primaryPressed: "#2F3273",
  action: "#F9DF77",            // 每頁唯一主要行動
  actionPressed: "#F3D45F",
  text: "#25285F",
  textSoft: "#6B6D88",          // 對白底 5.04:1、對暖米白 4.8:1
  border: "#E4E5F2",
  success: "#44B89A",
  successText: "#1E7A64",
  warning: "#E99A58",
  warningText: "#7A5E12",
  danger: "#D95D5D",            // 僅邊界與圖示（3.7:1，非文字元件達標）
  dangerText: "#B33C3C",        // 紅色文字要用這一階才過 4.5:1
  dangerBadge: "#C64848",       // 白字徽章底（4.75:1）
} as const;

/** 長輩端的暖光漸層。RN 需搭配 expo-linear-gradient。 */
export const elderGradient = {
  colors: [colors.backgroundWarmTop, "#F8F5FC", colors.background],
  locations: [0, 0.44, 1],
} as const;

/** 第一層｜系統態：由連線與錄音狀態決定，驅動狀態帶底色與角色光暈。
 *  沿用既有 TalkVisualState 的五個名稱，狀態機不動。 */
export const talkState = {
  idle:      { glow: "rgba(249,223,119,0.78)", pill: "#FDF6DE", ink: "#7A5E12" },
  listening: { glow: "rgba(77,80,162,0.34)",   pill: "#2F3273", ink: "#FFFFFF" },
  thinking:  { glow: "rgba(233,154,88,0.30)",  pill: "#FDF0E4", ink: "#B87333" },
  speaking:  { glow: "rgba(68,184,154,0.36)",  pill: "#EAF7F3", ink: "#1E7A64" },
  error:     { glow: "rgba(217,93,93,0.28)",   pill: "#FDF0F0", ink: "#B33C3C" },
} as const;

/** 第二層｜回應情緒：LLM 依長輩說的內容挑，只換角色本身。
 *  不得改變光暈色與狀態帶文字——那是 talkState 的職責。
 *
 *  識別字已核對 pet-core/emotions.js（18 個全數相符，裸名無前綴）。
 *  ⚠ blocked 必須擋在 sentiment.js 的本地關鍵詞比對「之後」，
 *    因為那一層也會挑到 angry（「生氣」「可惡」「討厭」等詞）。
 */
export const emotionPolicy = {
  layer: "avatar-only",   // 絕不碰 glow / pill / 狀態文案
  maxPerTurn: 1,
  fadeMs: 180,
  assertKeysExist: true,  // 開機檢查：每個 key 都要存在於 PET.EMOTIONS，對不上就 throw
  blocked: [
    // 對長輩本人的負面情緒：阿白不能對長輩不耐煩
    "angry", "furious", "annoyed", "disgusted",
    "jealous", "suspicious", "bored", "sulking",
    // 會嚇到人：長輩說胸口悶時要沉穩，慌張交給家屬端危急通知
    "panic", "shocked", "scared",
  ],
  preferred: {
    goodNews: ["celebrating", "touched", "proud"],
    discomfort: ["hurt", "apologetic"],
    lonely: ["lonely", "love"],
  },
} as const;

/** 角色插槽：直式 684 × 980，主舞台尺寸固定，永不縮放或位移。 */
export const avatar = {
  assetW: 684, assetH: 980,  // 素材基準（1 : 1.433），另出 @2x／@3x
  stageW: 209, stageH: 300,  // 對講機主舞台，永不縮放
  stageTop: 140,
  headerW: 34, headerH: 48,  // 頁首頭像（清單頁）
  rowW: 34, rowH: 48,        // 列內頭像
  dimmedOpacity: 0.68,       // 僅 error 狀態
} as const;

export const elder = {
  fontMin: 22,          // 硬底線，不設放大上限
  fontBig: 30,
  fontHuge: 40,
  pagePadding: 21,
  talkButton: 132,      // 主要態
  talkButtonSmall: 72,  // 阿白說話時的次要態
  roundButton: 60,      // 頁首圓鈕（之前聊過的、鈴鐺、返回）
} as const;

export const spacing = { xs: 4, s: 8, m: 16, l: 24, xl: 40 } as const;

export const radius = { card: 24, control: 16, pill: 999 } as const;

export const elevation = {
  row:     "0 2px 8px rgba(47,50,115,0.04)",
  card:    "0 8px 24px rgba(47,50,115,0.05)",
  overlay: "0 12px 32px rgba(47,50,115,0.08)",
  action:  "0 8px 20px rgba(214,168,32,0.28)",
  // 內容層蓋在角色前面時用雙向陰影，邊界才清楚
  sheet:   "0 10px 28px rgba(47,50,115,0.07), 0 -6px 18px rgba(47,50,115,0.04)",
} as const;

export const motion = {
  press: 120,    // 按下回饋（縮放 0.98）
  state: 200,    // 卡片淡入、狀態帶換色
  layout: 240,   // 頁面轉場、回話展開／收合、主鍵縮放
  chart: 300,
  easing: "ease-out",
} as const;
