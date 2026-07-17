/**
 * app（長輩／家屬 App，React Native ＋ Expo）的 eslint 設定。
 *
 * 以 eslint-config-expo 為底而非通用的 typescript-eslint：它懂 React Native
 * 慣例——例如 talk.tsx 載入音效的 require("@/assets/sounds/...")，通用設定會
 * 判它 no-require-imports 錯誤，但那是 RN 載入資產的標準寫法。假警報會訓練人
 * 忽略 linter。
 *
 * 版本由 `expo install` 挑選（eslint-config-expo ~10.0.0 對應 SDK 54）；npm 上
 * 的 57.x 是給更新的 SDK 用的，直接 `npm i` 會裝到不相容的版本。
 *
 * ⚠️ 兩個 react-hooks 版本並存，這是刻意的，見下方 REACT_COMPILER_RULES。
 */

const expoConfig = require("eslint-config-expo/flat");
const reactHooks = require("eslint-plugin-react-hooks");

// eslint-config-expo ~10.0.0 自帶巢狀的 eslint-plugin-react-hooks@5.2.0，且以
// 「react-hooks」這個名字註冊它。v5 只有兩條規則（rules-of-hooks、exhaustive-deps），
// 沒有 React Compiler 層——而 app.json 開了 experiments.reactCompiler，編譯器對
// 這些模式的假設就是它能否安全優化的前提，我們需要那一層。
//
// 三條路都試過，這是唯一沒有壞味道的：
//   1. 用同名註冊 v7 → eslint 拒絕（Cannot redefine plugin "react-hooks"）。
//   2. 用 npm overrides 強迫 expo 改用 v7 → 讓第三方設定跑在它沒測過的相依版本上，
//      且實測 overrides 未生效（巢狀仍是 5.2.0）。
//   3. ✅ 本檔：v7 以「react-compiler」之名另行註冊，只開它比 v5 多出來的規則。
//      經典層（rules-of-hooks、exhaustive-deps）仍由 expo 的 v5 管，不重複回報。
//
// 刻意手列而非沿用 v7 的 configs.recommended：後者把規則名寫死成 react-hooks/
// 前綴，在別的 plugin 名下無法套用；而且它含經典層，套下去會與 expo 的 v5 重複。
// 代價是升級 react-hooks 時這份清單要人工對一次上游的 recommended。
const REACT_COMPILER_RULES = {
  "react-compiler/config": "error",
  "react-compiler/error-boundaries": "error",
  "react-compiler/gating": "error",
  "react-compiler/globals": "error",
  "react-compiler/immutability": "error",
  "react-compiler/incompatible-library": "warn",
  "react-compiler/preserve-manual-memoization": "error",
  "react-compiler/purity": "error",
  "react-compiler/refs": "error",
  "react-compiler/set-state-in-effect": "error",
  "react-compiler/set-state-in-render": "error",
  "react-compiler/static-components": "error",
  "react-compiler/unsupported-syntax": "warn",
  "react-compiler/use-memo": "error",
};

module.exports = [
  // eslint-config-expo/flat 匯出的是設定陣列（13 段）而非單一物件，故須展開。
  ...expoConfig,
  {
    ignores: ["dist/*", ".expo/*", "expo-env.d.ts"],
  },
  {
    files: ["**/*.{ts,tsx}"],
    plugins: { "react-compiler": reactHooks },
    rules: REACT_COMPILER_RULES,
  },
];
