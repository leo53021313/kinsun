# Component Inventory

> 版本：v1.2｜日期：2026-07-30｜狀態：第二階段評審稿；已同步正式 A-Kin、對話 live region、提醒鈴鐺與統一行程
> 本文件只盤點與定義，不重構正式元件。沒有獨立 export 的 UI 一律標記「內嵌模式」，不冒充既有元件名稱。

## 1. As-is 元件盤點

| 元件／模式 | 現有檔案 | 使用頁面 | 類型 | 現有 Variant | 缺少 Variant | 狀態 | 無障礙 | 是否建議共用 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `Button` | `app/src/components/ui.tsx` | App 多數表單與操作 | Atom | default、disabled、busy | secondary、destructive、icon、full-width 規格 | `已實作` | role/button；busy 名稱與 state 待補 | 是 |
| `Field` | `app/src/components/ui.tsx` | App 登入、註冊、建立與管理表單 | Atom | label＋TextInput | error、helper、required、password reveal | `已實作` | 可見 label 未程式化關聯 | 是 |
| `ErrorText` | `app/src/components/ui.tsx` | App 表單／頁面錯誤 | Atom | 有訊息／不渲染 | alert、inline、banner、retry | `已實作` | 缺 live region／alert | 是 |
| `Section` | `app/src/components/ui.tsx` | 家屬首頁、詳情、管理 | Molecule | title＋children | collapsible、loading、error | `已實作` | 標題缺 header 語意 | 是 |
| `EmptyHint` | `app/src/components/ui.tsx` | 長輩清單、摘要、行程、通知／提醒 | Molecule | 純文字 | icon、primary action、secondary action | `已實作` | 可讀但無區域／狀態語意 | 是 |
| `AvatarPlaceholder` | `app/src/components/AvatarPlaceholder.tsx` | 長輩對話 | Atom／seam | idle、listening、thinking、speaking、error | reduced-motion | `已實作` | 已載入 A-Kin 靜態插畫；頁面層狀態帶提供 live region，VoiceOver／TalkBack 實機仍待驗證 | 僅 App |
| `MicIcon` | `app/src/components/MicIcon.tsx` | 長輩對話 | Atom | size、color | recording／disabled 規格不應只靠色彩 | `已實作` | 由父按鈕提供 label | 僅 App |
| `BellIcon` | `app/src/components/BellIcon.tsx` | 長輩對話提醒入口 | Atom | size、color、未讀 badge 由父層組合 | disabled／loading | `已實作` | 父按鈕提供「金孫的提醒」與未讀數 label，56dp | 僅 App |
| `RoleSwitcher` | `app/src/components/RoleSwitcher.tsx` | 內測 App | Molecule | 有另一 Session 時顯示 | busy、error、角色名稱更清楚 | `已實作` | role/button；點擊尺寸待查 | 僅內測 |
| 行程類型 Radio（內嵌） | App／LIFF schedules page | 統一行程管理 | Atom 模式 | 吃藥／回診／其他 | disabled、error、focus、large type | `已實作` | App 使用 radio state | 是 |
| 用藥時段 Chip（內嵌） | App／LIFF schedules page | 行程管理的吃藥類型 | Atom 模式 | selected／unselected | disabled、error、focus、large type | `已實作` | App 有 checkbox state；尺寸可能不足 | 是 |
| QR Code（內嵌／套件輸出） | Guardian home、Elder bind camera | 建立長輩、綁定 | Molecule | 顯示／掃描 | expired、copied、manual fallback | `已實作` | 需文字替代與代碼 | 是 |
| 通知／提醒項目（內嵌） | App guardian／elder notifications | 通知與金孫的提醒 | Molecule 模式 | 內容＋時間 | kind、severity、read、action | `已實作` | 型別不足；長輩版刻意不虛構分類 | 是，待 API 決策 |
| 長輩卡片（內嵌） | App／LIFF home | 長輩清單 | Molecule 模式 | 基本項目 | unread、stale、loading、error | `已實作` | 卡片可點，但名稱／hint 可更完整 | 是 |
| 摘要卡片（內嵌） | App elder detail | 長輩詳情 | Molecule 模式 | daily summary | loading、empty、error、new | `已實作` | heading／日期語意待補 | 是 |
| 行程項目（內嵌） | App／LIFF schedules | 統一行程管理 | Molecule 模式 | medication／appointment／custom、edit、delete、created_by elder | saving、error | `已實作` | 操作需包含內容與時間；長輩建立項需標示 | 是 |
| Admin 統計卡（內嵌） | `OverviewPage.tsx`＋`admin.css` | Admin overview | Molecule 模式 | metric／alert | loading、no-data、trend semantics | `已實作` | 趨勢與狀態不可只靠色彩 | 是（Admin） |
| Trace 階段項目（內嵌） | `TraceDetailPage.tsx` | Admin trace | Molecule 模式 | ok／error／missing data | pending、urgent、collapsed | `已實作` | 階段 heading、狀態文字、長內容焦點 | 是（Admin） |
| Admin error banner（CSS 模式） | 多個 Admin pages | Admin | Atom／Molecule 模式 | disconnected／load failed | retry、dismiss、warning／info | `已實作` | 需 role alert／status | 是（Web） |
| `useLoadable`／`usePolling` | `frontend/src/admin/` | Admin 多頁 | 行為 primitive | loading、error、data、polling | stale、manual retry 一致規格 | `已實作` | 不直接產生語意；由 UI 負責公告 | 是（Admin） |

## 2. 元件治理原則

1. 先抽出重複、已有兩處以上使用且狀態一致的模式；不為 Design System 完整度過度抽象。
2. React Native 與 Web 可共享名稱、狀態與 Token 語意，不強求共享同一份渲染程式碼。
3. 領域元件接收領域資料；foundation／atom 不知道 `elder_id` 等業務概念。
4. 所有 async 元件至少有 default、loading、error、disabled；清單型元件另有 empty。
5. destructive、permission、critical 都以文字與圖示表達，不只靠顏色。

## 3. 建議 Foundations

| Foundation | 用途 | 建議輸出 | Default／狀態概念 | 無障礙要求 | 現況／重構 |
| --- | --- | --- | --- | --- | --- |
| Typography | 建立一般、標題、長輩大字層級 | body、label、title、elder-primary、mono-data | 支援系統字級與合理 multiplier | 不把重要文案鎖死；行高隨字級 | theme 部分存在；需跨端語意化 |
| Spacing | 統一頁面、區塊、控制項節奏 | space-1…6 | 不因品牌變動 | 大字時允許垂直增長 | App 有 5 值；Web 未共用 |
| Color roles | 語意色而非品牌值 | surface、text、border、status-* | default、pressed、disabled、error | 對比達標；非唯一訊息 | App 有值；先改語意命名 |
| Radius | 控制項與 surface 結構 | control、surface、pill | 不代表最終風格 | 不影響焦點外框 | 多處硬編碼；需盤點 |
| Border | 分隔、控制項、焦點 | default、strong、focus | default、focus、error | 焦點可見且不只色彩 | App／Admin 各自定義 |
| Elevation | 區分 overlay／surface | none、overlay | 只保留結構級 | 不用陰影取代邊界 | 最終陰影暫不決定 |
| Motion | 即時回饋與狀態轉場 | instant、feedback、transition | loading、reduced motion | 尊重 reduced motion；不閃爍 | 尚未統一 |
| Touch target | 保證可操作尺寸 | 48pt、elder 104dp | default、compact 僅非核心 | 視覺與 hitSlop 都需檢查 | Button／mic 已有；Chip 待補 |
| Safe area | 頁面與固定 CTA 避讓 | page top／bottom、keyboard | portrait、keyboard | 大字與鍵盤下仍可達 | 各頁自行處理 |

## 4. 建議 Atoms

| 元件 | 用途／Props 與 Variant 概念 | 必要狀態 | Accessible name | 使用頁面 | 已存在 | 是否需重構 |
| --- | --- | --- | --- | --- | --- | --- |
| Button | `tone: primary/secondary/destructive`、`size: default/elder`、`busy` | default、pressed、disabled、loading、error 不由按鈕本身承擔 | 可見文字；icon-only 必填 label；busy 保留動作名稱 | 全端 | App 有 | 是，小幅擴充 |
| Icon Button | 返回、複製、次要工具；`icon`、`label`、`tone` | default、pressed、disabled、loading | 必填且包含目標，如「複製林阿嬤綁定碼」 | App／Web | 內嵌 | 是 |
| Text | 套用語意 Typography；`role`、`maxScale` 僅必要時 | default、muted、status | 由文字內容提供 | 全端 | 無獨立 | 視框架決定 |
| Field | `label`、`value`、`helper`、`error`、`required`、`secure` | default、focus、disabled、loading、error、empty | label 與 input 程式化關聯 | 全表單 | App 有 | 是，P1 |
| Error Message | inline／summary／banner；可選 retry | hidden、error、recovering | alert 或 live region，內容含下一步 | 全端 | App／Admin 模式 | 是，P1 |
| Badge | unread、severity、status；文字＋圖示 | default、selected、error | 完整狀態名稱，不只數字 | 首頁、通知、Admin | 內嵌 | 是 |
| Divider | 分區與群組 | default、strong | 裝飾性時隱藏於 SR | 列表／表單 | 內嵌 | 否，低優先 |
| Spinner | 小／大；可伴隨文字 | loading、inline | 「正在載入…」；避免重複公告 | 啟動、async 操作 | 多處 | 是 |
| Chip | selectable／filter／status；`selected` | default、pressed、selected、disabled、error | checkbox／radio 語意＋label | 行程類型、用藥時段、Admin filter | 內嵌 | 是，P1 |

## 5. 建議 Molecules

| 元件 | 用途／Props 與 Variant 概念 | 必要狀態 | Accessible name | 使用頁面 | 已存在 | 是否需重構 |
| --- | --- | --- | --- | --- | --- | --- |
| Form Row | label＋control＋helper＋error | default、focus、disabled、error、empty | label 綁 control；錯誤以 described-by | 登入、註冊、管理 | 部分 | 是 |
| Empty State | title、body、primary／secondary action | empty、loading 不混用 | 區域標題＋下一步 | 各清單／區塊 | `EmptyHint` | 是 |
| Status Banner | info、warning、error、success、permission | default、loading、error、dismissed | status／alert；訊息含行動 | 權限、通知、Admin | 內嵌 | 是，P1 |
| Notification Row | elder、time、content、kind、severity、read | default、unread、read、error | 誰／何時／事件／狀態 | 通知 | 內嵌 | 是；先決 API |
| Schedule Row | kind、title、occurrences、created_by、edit／delete | default、saving、error、empty 不在 row | 「編輯／刪除＋內容＋時間」 | App／LIFF | 內嵌 | 是 |
| Elder Card | elder name、last update、unread／new event | default、pressed、loading、error | 「開啟＋長輩名＋新事件」 | 家屬首頁、LIFF、Admin | 內嵌 | 是 |
| Permission Status | permission、reason、primary recovery、optional state | requesting、granted、denied、limited | 權限名稱、影響、下一步 | bind／talk | 內嵌 | 是，P1 |

## 6. 建議 Organisms

| 元件 | 用途／Props 與 Variant 概念 | 必要狀態 | Accessible name | 使用頁面 | 已存在 | 是否需重構 |
| --- | --- | --- | --- | --- | --- | --- |
| Voice Interaction Panel | A-Kin、reply、mic、提醒鈴鐺、permission、conversation state | Idle、Listening、Thinking、Speaking、Error、permission denied、403 | 頁面狀態帶已有 live announcement；mic／bell label 隨狀態與未讀數改變；需補 VoiceOver／TalkBack 實機驗證 | `/elder/talk` | 頁面內嵌 | 是，P0／P1 |
| Guardian Elder Summary | report、summary、schedules、new event | loading、partial、normal、empty、error | 各區 heading 與更新時間 | 長輩詳情 | 頁面內嵌 | 是，支援局部失敗 |
| Binding Code Panel | QR、manual code、expiry、copy、instructions | loading、active、copied、expired、error | 代碼用途與到期；QR 有文字替代 | 家屬首頁／詳情 | 內嵌 | 是 |
| Health Report Section | risks、reminders、period、privacy note | loading、normal、empty、error | 期間、事件數、嚴重度文字 | App／LIFF／Admin | 內嵌 | 是 |
| Admin Trace Timeline | ordered stages、status、latency、raw identifiers | loading、partial、ok、error、empty | 階段 heading、狀態、第一個失敗 | Admin trace | 頁面內嵌 | 是（Admin） |

## 7. 元件狀態最低合約

| 元件類型 | Default | Pressed | Disabled | Loading | Error | Empty |
| --- | --- | --- | --- | --- | --- | --- |
| 操作控制 | 可互動 | 視覺＋狀態回饋 | 原因可理解 | 防重送且保留名稱 | 由鄰近訊息說明 | 不適用 |
| 輸入控制 | 值與 label | focus／active | 保留可讀值 | 通常鎖定並說明 | 欄位＋摘要 | 空值有 placeholder，但 label 仍存在 |
| 清單／區塊 | 資料 | 項目 pressed | 操作可局部停用 | skeleton／文字 | 保留既有資料＋重試 | 說明原因＋主要下一步 |
| 狀態／Banner | 資訊 | 可選 action pressed | action 可停用 | recovering | alert | 通常不適用 |

## 8. 建議重構優先序

1. **P0／P1**：Voice Interaction Panel 的權限與 403 回復，以及已實作動態公告的 VoiceOver／TalkBack 實機驗證。
2. **P1**：Field／Error Message／Section heading 的可存取語意。
3. **P1**：Status Banner、Empty State 與各區局部 loading／error 合約。
4. **P1**：Chip、日期控制與 destructive action 的 48pt、label、確認。
5. **P1**：Admin tab semantics 與 Trace stage 結構。
6. **P2**：跨端共用命名與 foundation Token；不在此階段共享渲染程式碼。
