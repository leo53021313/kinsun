# 無障礙與適老化檢查

> 版本：v1.3｜日期：2026-07-30｜狀態：第二階段評審稿；已同步五態、對話 live region 與長輩提醒入口
> 分級：P0 阻止核心任務或造成安全／隱私風險；P1 明顯降低可用性；P2 品質改善。此為程式碼與線框稽核，不等於 VoiceOver、TalkBack 與真實長輩實機測試已完成。

## 1. 摘要

### 已有基礎

- App `Button` 最小高度 48pt。`已實作`
- 長輩麥克風主按鈕為 104dp；提醒鈴鐺為 56dp，兩者都有 `accessibilityRole="button"` 與 label。`已實作`
- 錄音開始／停止已有觸覺與音效。`已實作`
- 長輩字級已有 22／30／40 Token，回覆可捲動。`已實作`
- 用藥時段 Pressable 有 checkbox role 與 checked state。`已實作`
- 用藥／回診刪除使用系統確認框。`已實作`
- App 使用明亮高對比色組；主要文字組合的靜態對比抽查高於 4.5:1。`已實作`
- 對話狀態帶已有 `accessibilityLiveRegion`，麥克風同步提供 label、disabled 與 busy state。`已實作`

### 最大缺口

1. 權限與 403 回復不完整；動態對話狀態雖已有 live region，仍缺 VoiceOver／TalkBack 完整實機驗證。
2. `Field`、`ErrorText`、`Section` 等共用元件的語意不足，影響多頁。
3. 48pt 尚未覆蓋 Chip、日期控制、部分 Web／Admin 操作。
4. LIFF 幾乎使用原生預設 UI，表單、busy、error、confirm 與焦點基線不足。
5. 通知資料契約不能可靠表達嚴重度與單筆已讀，屬安全性 P0 待決策。

## 2. 問題清單

| ID | 級別 | 檢查項目 | 現況與問題 | 影響 | 建議 | 驗證方式 |
| --- | --- | --- | --- | --- | --- | --- |
| A11Y-01 | P0 | 麥克風權限拒絕 | 對話頁只設定文字且停用麥克風，缺「開設定／重新檢查」。 | 長輩無法完成唯一核心任務。 | Status Banner＋開設定主 CTA＋回 App 後重新檢查。 | iOS／Android 首次拒絕、永久拒絕、重新允許。 |
| A11Y-02 | P0 | 403 回復 | replyText 後立即 sign-out，路由可能先導離。 | 看不到原因，不知道要重登或重綁。 | 將 recovery reason 帶到持續畫面；一主一次回復路徑。 | 模擬 turn 403，確認 Screen Reader 與視覺都能完成回復。 |
| A11Y-03 | P0 | 危急通知嚴重度 | API 只有內容與時間，UI 無可靠 kind／severity。 | 可能延誤或過度反應；只改色也無法解決。 | 先拍板資料契約；文字標籤＋圖示＋下一步。 | 契約測試＋文案理解測試，不以色彩辨識。 |
| A11Y-04 | P0 | 隱私 | 家屬端若誤用 Admin／turn 資料會暴露逐字稿。現況頁面未暴露。 | 隱私與同意風險。 | 保持資料層與 IA 邊界；家屬元件不接受 transcript prop。 | 路由／型別／畫面 content audit。 |
| A11Y-05 | P1 | 動態狀態 | Idle／Listening／Thinking／Speaking／Error 已由狀態帶 live region 公告，mic label／state 也同步；尚未跑 VoiceOver／TalkBack 完整一輪。 | 尚不能確認公告時機、重複讀取與核心任務可完成性。 | 以兩套 Screen Reader 實測；若有重複公告再加入節流，不先假設已通過。 | 關閉視覺，僅用 SR 完成錄音、等待、播放、純文字 reply 與錯誤回復。 |
| A11Y-06 | P1 | Field label | `Field` 把 Text label 與 TextInput 相鄰放置，沒有明確關聯。 | SR 可能只讀 placeholder；錯誤與欄位脫節。 | 原生端用 `accessibilityLabel`／described-by 可用策略；Web 用 `label for`。 | 掃描登入、註冊、用藥、回診表單。 |
| A11Y-07 | P1 | 錯誤訊息 | `ErrorText` 沒有 alert/live region；錯誤多在頁首。 | 送出後使用者不知道發生錯誤。 | 錯誤摘要設 alert，焦點移入；欄位錯誤提供關聯。 | 鍵盤／SR 送出每種錯誤。 |
| A11Y-08 | P1 | Heading／Landmark | `Section` 標題沒有 header 語意；Admin tabs／sections 亦不完整。 | 難以快速跳轉長頁面。 | App heading role；Web 使用 h1–h3、main、nav。 | SR heading rotor／landmark 導覽。 |
| A11Y-09 | P1 | 字級放大 | App 多個 13–18px 硬編碼；表單與固定區未全數驗證。 | 200% 或大字時截斷、重疊、CTA 被推走。 | 語意 type Token、允許垂直增長、ScrollView 與 safe area。 | iOS 最大字級、Android font scale 2.0、320px。 |
| A11Y-10 | P1 | 文字截斷 | 內測狀態、邀請碼、通知、日期與長回覆可能在窄寬度擁擠。 | 關鍵資訊不完整。 | 關鍵文字不設單行截斷；代碼分組；次要資料可折行。 | 320px、繁中長姓名、長 API 訊息。 |
| A11Y-11 | P1 | 48pt 點擊區 | Button 與 mic 合格；Chip、日期控制、RoleSwitcher、Web controls 可能不足。 | 手部穩定度或低視力使用者易誤觸。 | 所有 interactive box min 48；必要時擴 hitSlop。 | 自動量測＋實機顯示點擊框。 |
| A11Y-12 | P1 | 104dp 語音按鈕 | 尺寸合格；Thinking／Speaking 是否可點與 disabled 狀態需清楚。 | 重複錄音或不知道為何不能按。 | 禁用時文字說明；不只降低透明度；狀態 label 更新。 | 全狀態逐一讀取 name／role／state。 |
| A11Y-13 | P1 | 鍵盤遮擋 | 登入、註冊、綁定、帳密代辦、用藥、回診未一致使用 keyboard avoidance。 | 輸入或主要 CTA 看不到。 | Focus-aware ScrollView／KeyboardAvoidingView；不要固定 CTA 蓋鍵盤。 | 小手機、橫向、第三方鍵盤。 |
| A11Y-14 | P1 | 操作順序 | 對話、詳情長頁與 Admin tabs 未定義一致焦點順序。 | 鍵盤／SR 順序與視覺順序不一致。 | DOM／RN tree 順序對齊；overlay 開啟時 focus trap／restore。 | Tab／swipe 全頁巡覽。 |
| A11Y-15 | P1 | 長文字與 ScrollView | 對話已可捲動，但固定 mic 與大字組合需驗證；詳情與表單亦可能很長。 | 最後一段或 CTA 被截斷。 | bottom inset 等於固定區高度；焦點自動捲入視野。 | 3 倍回覆、最大字級、鍵盤。 |
| A11Y-16 | P1 | 音效／觸覺非唯一回饋 | 現況有文字、形狀／動作與 live region；實際 Screen Reader 公告尚未驗證。 | 聽不到、感覺不到或裝置靜音時，仍可能因公告時機不佳而失去訊息。 | 保持多通道回饋，並以實機確認公告順序與可理解性。 | 關音量、關震動、閉眼與 Screen Reader 四種測試。 |
| A11Y-17 | P1 | 刪除確認 | App 有系統確認；LIFF 沒有一致確認。按鈕可能只寫通用刪除。 | 誤刪照護資料與提醒。 | 目標名稱＋影響；取消為安全預設；destructive label。 | 用相似名稱項目測試。 |
| A11Y-18 | P1 | Admin tabs | 五分頁用一般 button，無 tablist／tab／tabpanel、aria-selected、方向鍵。 | 鍵盤與 SR 難理解選取狀態。 | 套用 ARIA tab pattern；焦點與 activation 策略一致。 | 鍵盤左右鍵、Home／End、SR。 |
| A11Y-19 | P1 | Admin／LIFF focus | CSS 未集中定義可見 focus；LIFF 依瀏覽器預設。 | 鍵盤使用者可能找不到焦點。 | `border-focus`／outline＋offset；不要移除預設而無替代。 | 全頁 Tab 與高對比模式。 |
| A11Y-20 | P1 | Loading／busy | App Button busy 以 spinner 取代文字；頁面 loading 未全有可讀名稱。 | 不知道哪個動作正在處理。 | 保留「正在登入／正在儲存」名稱，設 busy，完成後公告。 | 慢速網路與重複點擊測試。 |
| A11Y-21 | P2 | 對比 | 目前主要文字組合良好；border、disabled、badge、Admin 多色組合未全面量測。 | 低視力下邊界或狀態難辨。 | 第三階段對所有狀態組合自動檢查；border 另做非文字對比。 | Token matrix＋高對比模式。 |
| A11Y-22 | P2 | 認知負荷 | 家屬首頁同時含清單、通知、新增、同意、QR 與登出；詳情資訊多。 | 初次建立時負荷高。 | 漸進揭露：建立結果 panel、照護區塊與次要操作分組。 | 首次使用與多人照護任務測試。 |
| A11Y-23 | P2 | 技術用語 | 內測可見權限／trace 用語合理；長輩錯誤仍可能接近後端語意。 | 長輩被技術訊息嚇到。 | 長輩端只說原因、影響、下一步；錯誤碼留給 Admin。 | 文案理解訪談。 |
| A11Y-24 | P2 | 誤觸風險 | 登出、刪除、重設帳密與語音主操作距離與層級未全面檢查。 | 中斷 Session 或改掉照護資料。 | destructive 降階、留空間、確認後果；不與主 CTA 緊鄰。 | 手部穩定度情境測試。 |

## 3. 長輩端適老化逐項檢查

| 項目 | As-is | 線框要求 | 結果 |
| --- | --- | --- | --- |
| 看得清楚 | 22／30／40 Token；高對比 | 320px＋大字仍可捲動、不截斷 | 需實機驗證 |
| 按得到 | Button 48、mic 104 | Chip／次要操作也要 48 | 部分通過 |
| 聽得懂回饋 | 錄音音效、TTS | 同步文字與人話錯誤 | 部分通過 |
| 知道系統狀態 | 五種 Avatar state、reply text、live region、按鈕 state | VoiceOver／TalkBack 完整一輪 | 已實作，待實機驗證 |
| 權限回復 | 文字錯誤 | 開設定、重試、定位可繼續 | 待補 |
| 不被技術訊息嚇到 | strings 多為繁中 | 移除 403／permission 技術詞 | 需文案測試 |
| 重要操作非單一手勢限定 | 可按住放開或短按兩次 | 兩種方式都需可發現，Listening 文案必須反映目前模式 | 待實機研究 |

### 雙手勢研究風險

正式 App 已實作兩種方式：按住達 500ms 後放開送出，以及短按一次開始、再按一次送出。雙手勢降低單一持續手勢的門檻，但也增加理解與模式辨識負擔；第三階段應先測試：

- 未教學時首先發現哪一種方式，以及能否完成整輪對話。
- 短按第一次放開後，是否理解系統仍在聆聽，並自行找到第二次按下。
- 長輩是否能穩定按住 2–10 秒，並理解放開等於送出。
- 手部穩定度或 Screen Reader 操作是否使其中一種方式明顯較容易。

研究完成前不宣告偏好手勢，也不因其中一種方式表現較好就直接移除另一種；需回看任務完成、錯誤型態與受試者原意。`待研究`

## 4. Screen Reader 狀態語句

| 狀態 | 建議公告 |
| --- | --- |
| Idle | 「可以說話了。可按住麥克風，或按一下開始、說完再按一下。」 |
| Listening（按住） | 「正在錄音。說完後放開。」 |
| Listening（短按） | 「正在錄音。說完後再按一下。」 |
| Thinking | 「錄音已送出，正在準備回答。」 |
| Speaking | 「正在播放回答。畫面也有文字。」 |
| Error | 「金孫沒聽清楚。請再說一次。」 |
| Mic denied | 「麥克風未開啟，現在不能錄音。可開啟手機設定。」 |
| Location denied | 「定位未開啟，仍可繼續聊天。」 |
| Network error | 「剛才沒有送成功。請再錄一次。」 |
| 403 | 「這台手機的綁定已失效。可用帳密登入或重新綁定。」 |

公告須節流，避免每次 render 重複讀取；長回覆由使用者自行閱讀，不一次以 live region 朗讀全文。

## 5. 鍵盤與焦點順序

### Expo App

1. 頁面標題。
2. 說明／錯誤摘要。
3. 依視覺順序的欄位與 helper／error。
4. 主要 CTA。
5. 次要操作。

錯誤送出後先公告摘要，再讓使用者前往第一個錯誤欄位。權限 dialog 關閉後焦點回到觸發位置；403 回復頁第一個焦點是原因標題。

### LIFF／Admin

- 保留原生 Tab 順序，不使用正 tabindex。
- 主導航前提供 skip-to-main。
- polling 更新不移動焦點；新訊息以可選 status 公告。
- Admin tabs 使用方向鍵移動，同時維持 `aria-selected` 與 panel 關聯。
- Trace 長內容可收合時，按鈕名稱需包含階段與目前狀態。

## 6. 驗證矩陣

| 環境 | 最低測試 |
| --- | --- |
| iOS | VoiceOver、最大 Dynamic Type、粗體文字、降低動態效果、麥克風／定位拒絕與重新允許。 |
| Android | TalkBack、font scale 2.0、顯示大小放大、移除動畫、權限「這次允許／不允許」。 |
| 320px 手機 | 對話、綁定、所有主要 CTA、鍵盤與長錯誤訊息。 |
| LIFF WebView | 外接鍵盤、螢幕閱讀器、放大 200%、瀏覽器返回、慢速網路。 |
| Admin 桌機 | 純鍵盤、200% zoom、Windows 高對比、螢幕閱讀器、polling 更新。 |

## 7. 完成門檻

- 所有 P0 關閉，或由產品／安全負責人書面接受風險。
- 長輩核心 Task Flow 可只靠 VoiceOver／TalkBack 完成。
- 所有核心操作至少 48pt；mic 保持 104dp。
- 最大字級下關鍵資訊、錯誤與 CTA 不截斷。
- 色彩移除後仍可辨識狀態與嚴重度。
- 家屬端未出現完整逐字對話。
- 通知 kind／severity 未拍板前，不把概念線框宣告為可實作完成。
