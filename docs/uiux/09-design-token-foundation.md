# Design Token Foundation

> 版本：v1.1｜日期：2026-07-30｜狀態：第二階段評審稿；已同步對講機限定 token 與 A-Kin
> 本文件把「目前實作值」與「結構性建議」分開；`talkColors` 是核准且已實作的對講機頁面色盤，但不外推為三端最終品牌。

## 1. As-is Token：Expo App

### 1.1 `app/src/lib/theme.ts`

| 現有 key | 目前值 | 使用語意 | 備註 |
| --- | --- | --- | --- |
| `colors.background` | `#FFF9F0` | 頁面背景 | 目前實作，不是最終品牌色。 |
| `colors.surface` | `#FFFFFF` | 卡片／輸入／控制項背景 | 結構角色可保留，值待視覺階段。 |
| `colors.primary` | `#C2410C` | 主要 CTA、選取 | 目前暖磚橘；不是品牌定案。 |
| `colors.primaryPressed` | `#9A3412` | pressed | 狀態角色可保留。 |
| `colors.text` | `#1C1917` | 主要文字 | 目前實作。 |
| `colors.textSoft` | `#57534E` | 次要文字 | 目前實作。 |
| `colors.border` | `#E7E5E4` | 邊界 | 對低視力使用者可能偏淡，需實機檢查。 |
| `colors.danger` | `#B91C1C` | 錯誤／危急 | 不得作唯一嚴重度訊號。 |
| `colors.success` | `#15803D` | 成功／正常 | 不得把「無資料」套用 success。 |
| `elder.fontMin` | `22` | 長輩最小字 | 系統字級放大後仍需驗證版面。 |
| `elder.fontBig` | `30` | 長輩主要字 | 對話 reply 等。 |
| `elder.fontHuge` | `40` | 長輩大標題 | 角色頁另以 `+16` 形成 56。 |
| `spacing.xs` | `4` | 微小間距 | 目前實作。 |
| `spacing.s` | `8` | 小間距 | 目前實作。 |
| `spacing.m` | `16` | 一般間距 | 目前實作。 |
| `spacing.l` | `24` | 大間距 | 目前實作。 |
| `spacing.xl` | `40` | 區塊／頁面間距 | 目前實作。 |

### 1.2 對講機限定 `talkColors`

| 現有 key | 目前值 | 使用語意 |
| --- | --- | --- |
| `talkColors.ink`／`paper` | `#171D2A`／`#FFFDF8` | 對講機主要文字與紙白背景 |
| `talkColors.blue`／`yellow`／`coral` | `#76BDF0`／`#FFC928`／`#FF6A33` | A-Kin 介面辨識與主要操作 |
| `talkColors.thinking`／`speaking` | `#F7D984`／`#A6D7B9` | 處理中／播放中狀態帶 |
| `talkColors.error`／`errorText` | `#FFD2C7`／`#7B1E1A` | 錯誤背景與高對比文字 |

這組 token 只套用 `/elder/talk`；家屬端仍使用全域 `colors`。`已實作`

### 1.3 目前對比抽查

以目前 hex 值依相對亮度計算：

| 前景／背景 | 對比 |
| --- | --- |
| primary／surface | 5.18:1 |
| primaryPressed／surface | 7.31:1 |
| text／background | 16.71:1 |
| textSoft／background | 7.29:1 |
| danger／surface | 6.47:1 |
| success／surface | 5.02:1 |

上述只證明這些色組合的靜態數值；不代表所有透明度、disabled、border、圖示或實機顯示都通過，也不等於色彩可單獨傳遞狀態。

### 1.4 App 硬編碼尺寸

| 類型 | 目前值／例子 | UX 影響 |
| --- | --- | --- |
| 主要 touch target | `Button minHeight: 48` | 符合本專案最低基線。 |
| 長輩語音按鈕 | `104 × 104`、radius 52 | 已符合文件決議。 |
| 長輩提醒鈴鐺 | `56 × 56` | 高於 48pt 基線；未讀 badge 不只靠色彩。 |
| A-Kin 角色區 | 寬度 `100%`、`maxWidth: 285` | 靜態插畫透過既有 Avatar seam 呈現五態。 |
| 圓角 | 12、14、16、22、52、90、999 | 語意尚未收斂。 |
| 一般字級 | 13、14、16、17、18、20、26 | 過多單點值；13px 內測／時間文字需放大檢查。 |
| 長輩字級 | 22、30、40；角色標題 56 | 有層級，但需定義行高與縮放策略。 |
| 邀請碼 | 26、weight 800、letter spacing 1 | 需等寬感與讀碼分組，不需指定品牌字體。 |
| 用藥 Chip | padding 依 spacing、radius 999 | 視覺高度可能小於 48pt。 |
| 日期控制 | padding、radius 12、font 18 | 需確認整體可點擊高度。 |
| 卡片 | radius 16、padding 16／24 | 重複模式可語意化為 surface token。 |

### 1.4 Loading／Error

- App spinner 色使用 `primary` 或白色；busy 時文字被 spinner 取代。`已實作`
- 錯誤文字使用 `danger`，沒有統一背景、border、live region 或 retry spacing。`已實作`
- loading／empty 多以 `EmptyHint` 或 `ActivityIndicator` 表達；缺 skeleton 與局部狀態規格。`已實作`

## 2. As-is Token：LIFF 與 Admin

### LIFF

- 沒有獨立產品 CSS 或 Token；主要呈現依瀏覽器預設。`已實作`
- HTML input、button、list 與 heading 沒有跨端 spacing、touch target、focus 或 error 角色。`已實作`

### Admin

| 類型 | 目前值／例子 |
| --- | --- |
| 頁面背景／文字 | `#f5f6f8`／`#1f2933` |
| 主導航 | `#1f2933`；文字 `#fff`／`#cbd2d9` |
| content max width | `960px` |
| key form max width | `360px` |
| surface | `#fff`、radius `8px`、padding `1rem` |
| badge | blue `#3b82f6`、green `#10b981`、red `#ef4444`、purple `#8b5cf6` |
| error banner | `#fef2f2` 背景、`#b91c1c` 文字 |
| trace | 左側 3px 狀態線、error 改紅 |
| 操作 | 多個 `rem` spacing 與原生 button；focus token 未集中 |

Admin 顏色是目前內部工具實作，不是 App 品牌延伸。LIFF／Admin 不應直接複製 App 色值，只需先共享語意角色與可用性基線。

## 3. 建議 Foundation Token

以下值是結構性 baseline，可在第三階段視覺探索後調整名稱對應值；色彩欄只定義角色，不決定最終 hex。

### 3.1 Spacing

| Token | 建議值 | 用途 |
| --- | --- | --- |
| `space-1` | 4 | 圖示與短標籤內部。 |
| `space-2` | 8 | 同群小間距。 |
| `space-3` | 12 | 控制項內部或緊密 row。 |
| `space-4` | 16 | 一般卡片／頁面間距。 |
| `space-5` | 24 | 區塊與表單群組。 |
| `space-6` | 32 | 大區塊。 |
| `space-7` | 40 | 長輩端頁面主要留白。 |

### 3.2 Typography

| Token | 結構建議 | 用途 |
| --- | --- | --- |
| `font-caption` | 13／18；非關鍵資訊 | 時間、內測資料；不得承載唯一重要訊息。 |
| `font-label` | 16／22、semibold | 欄位與控制項。 |
| `font-body` | 17／26 | 家屬 App 正文。 |
| `font-title` | 24／32、bold | 一般頁面標題。 |
| `font-elder-primary` | 22／32 起 | 長輩最小核心文字。 |
| `font-elder-action` | 30／40、bold | 主要動作與回覆。 |
| `font-elder-display` | 40／48、bold | 少量大標；不可用於長段落。 |
| `font-data-mono` | 系統等寬 fallback | trace id、代碼；不加入字型檔。 |

所有文字預設支援系統字級；若因內測密度限制 multiplier，必須有明確理由，且不能套用長輩核心文案。

### 3.3 Touch、尺寸與安全區

| Token | 建議值／定義 | 用途 |
| --- | --- | --- |
| `touch-min` | 48pt | 所有核心與次要可點擊目標。 |
| `touch-elder-primary` | 104dp | 長輩語音主按鈕。 |
| `control-height-default` | min 48 | input、button、Chip。 |
| `page-gutter-mobile` | 16；320px 可降 14 | 手機左右安全留白。 |
| `safe-area-page` | 平台 safe area inset＋page gutter | 頁首與固定 CTA。 |
| `keyboard-avoidance` | focus control＋primary CTA 可見 | 表單畫面行為 token。 |
| `content-max-width-form` | 520px | Web 表單。 |
| `content-max-width-admin` | 960px（as-is 起點） | Admin 主內容；寬表格可另定。 |

### 3.4 Radius、Border、Elevation

| Token | 建議起點 | 用途 |
| --- | --- | --- |
| `radius-control` | 12 | input／button。 |
| `radius-surface` | 16 | card／section。 |
| `radius-pill` | 999 | Badge／Chip；語意命名，不代表每處使用。 |
| `border-default` | 1px solid semantic border | 一般邊界。 |
| `border-strong` | 2px solid semantic strong | 高辨識區塊。 |
| `border-focus` | 2px＋offset | 鍵盤／輔助操作焦點。 |
| `elevation-overlay` | 暫以邊界＋遮罩表達 | 權限說明、確認；最終陰影待視覺階段。 |

### 3.5 Motion

| Token | 建議值 | 用途 |
| --- | --- | --- |
| `duration-instant` | 0–80ms | pressed 等立即回饋。 |
| `duration-feedback` | 120–180ms | 狀態確認。 |
| `duration-transition` | 180–240ms | 非核心區塊展開。 |
| `motion-reduced` | 移除位移／循環動畫 | 尊重系統 reduced motion。 |

對話 Thinking 不使用快速閃爍；音效、觸覺與動畫都不能取代文字狀態。

### 3.6 Color roles（只定義角色）

```text
color-bg-page
color-bg-surface
color-text-primary
color-text-secondary
color-border-default
color-border-focus
color-action-primary
color-action-primary-pressed
color-action-disabled
color-status-info
color-status-warning
color-status-danger
color-status-success
color-status-on-fill
```

每個 status 同時搭配文字標籤與圖示／形狀；disabled 仍需可讀，且不得是唯一阻止錯誤的驗證方式。

## 4. As-is → Foundation 對照

| As-is | 建議語意 Token | 處理 |
| --- | --- | --- |
| `spacing.xs/s/m/l/xl` | `space-1/2/4/5/7` | 保留值並補 12／32 級距。 |
| `elder.fontMin/Big/Huge` | `font-elder-primary/action/display` | 補行高、權重與縮放規則。 |
| `colors.primary` | `color-action-primary` | 只映射角色；hex 不視為定案。 |
| `colors.danger` | `color-status-danger` | 加文字、圖示、border pattern。 |
| 12／14／16／22／999 radius | control／surface／pill | 14／22 是否保留待元件實作時收斂。 |
| `minHeight: 48` | `touch-min`／`control-height-default` | 擴大到 Chip、日期與所有 icon button。 |
| mic `104` | `touch-elder-primary` | 保留結構值。 |
| Admin `max-width: 960px` | `content-max-width-admin` | 作 as-is 起點，寬表格另測。 |

## 5. 暫不決定

- 最終 Primary Color、Secondary Color 與所有品牌色票。
- 品牌漸層、Logo 色、App Icon 色。
- 虛擬角色、插畫與攝影風格。
- 最終字體家族與付費字型。
- 最終陰影、玻璃效果、材質與裝飾性 motion。
- 深色模式；目前文件決議不做，但第三階段若範圍變更需另行評估。

## 6. 後續實作建議

1. 先在 TypeScript 定義語意 Token schema，再逐頁映射；不要一次大規模改樣式。
2. App 先處理 touch、type、status、safe area；LIFF／Admin共享命名但各自渲染。
3. 為每個 Token 加使用例與禁用例，避免 `danger` 同時代表醫療嚴重度與一般表單錯誤。
4. 第三階段視覺方向選定後，再填 color role 的最終值並做全組合對比驗證。
