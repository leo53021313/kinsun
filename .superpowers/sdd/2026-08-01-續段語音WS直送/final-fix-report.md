# 續段語音 WS 直送 — 最終審查修復報告

- **日期**：2026-08-01
- **分支**：`Leo`（未 push、未切分支、未改寫歷史）
- **基準**：`e29322c`
- **commit**：`20b81f5`／`fad52c3`／`2c178d5`／`03f3db4`
- **狀態**：2 Critical＋3 Important＋4 次要全部處理完畢，全套測試綠

---

## 0. 一句話結論

兩個 Critical 都在**修好之前實測會紅**，而且紅出來的症狀與審查員描述一字不差；
Important 3 我實機跑了 Opik，**審查員的推測是對的**，設計文件 §5.5 的宣稱已依實測更正。

---

## 1. 逐項修法與理由

### 🔴 Critical 1：續段拿錯文字來源（commit `20b81f5`）

**根因那一行**：`ws.py:516`（修前）`_push_continuation_chunks(sender, collector.text, turn_id)`。
`collector.text` 由 `inbound.py::_compose_text` 填入，`show_transcript` 為真時是
`"辨識：…\n\n回復：…"`；而 `pipeline._synthesize` 切的是 `reply_text`。同一輪的兩組段落
因此不同源。

**修法**：`DeliveryOutcome` 新增 `reply_text` 欄位，在 `_run_pipeline` 裡與 `chunk_count`／
`reply_digest` **同一行、從同一個 `result.text`** 填入；`ws.py` 改傳 `outcome.reply_text`。

**為什麼選這個而不是讓 `_TurnCollector` 另存欄位**：「宣告了幾段」與「那幾段是從哪串文字
切出來的」必須同源。放在 `DeliveryOutcome` 讓兩者住同一個 frozen dataclass、由同一行程式
一起產生，之後不可能分岔；讓 collector 另存一份則是把同一個事實存在兩個地方，正是這次
出事的形狀。`collector.text` 的既有行為**一字未動**，`reply` 訊框的字幕仍照舊帶 debug 前綴
（依指示不改變顯示字串行為）。

⚠️ 兩處補上明文警告（`_TurnCollector.text` 的 docstring、`_push_continuation_chunks` 的
docstring），因為 `speech/chunking.py:75-78` 早在 2026-07-26 就寫過同一個警告卻沒擋住第二次。

### 🔴 Critical 2：終止訊框把字幕清空（commit `fad52c3`）

**根因那一行**：`useTalk.ts:546`（修前）`if (canTakeOverSubtitle) { setReplyText(frame.text); }`
——終止訊框的 `frame.text` 是 `""`。空音檔讓它不進播放佇列（`talkSocket.ts` 把 `audio_url`
改成 `""`），但擋不住它先走過這三行。

**修法**：`if (canTakeOverSubtitle && frame.text)`。

**為什麼選守門而不是「終止訊框提早 return」**：播放回呼那一側（`useTalk.ts:406`）本來就是
`if (item.text)`，兩邊寫成同一個形狀表達的是同一條規則——**空字串不代表內容，代表沒有內容**。
早退路徑則是新增一條 `is_last` 專屬分支，而 Task 5 的審查才剛因為「chunk 專屬分支與通用邏輯
重複」把一條分支砍掉（commit `6eed0e2`）；再開一條是走回頭路，且未來想在終止訊框上掛別的
行為的人得先拆掉它。

### 🟠 Important 1：`in_flight` 延後釋放（commit `2c178d5`）

**修法**：`in_flight.finish(turn_id)` 前移到續段迴圈之前（仍在 `turn_gate.admit()` 之內）。

- ⚠️ **只搬在途清單的名額**；容量閘門名額仍照 D-2 保留到續段跑完（續段一樣打 GPU）。
  兩者是不同的東西，程式碼註解已寫明不可一起搬。
- `finally` 那一行**刻意保留**：`_InFlight.finish` 冪等（`pop` 給預設值＋`in` 判斷），
  而失敗與排隊逾時兩條路徑走不到前移的那一行，刪掉會讓它們漏掉解除——那正是這一行最初
  存在的理由。
- **已確認 `_LATE_REPLY_DIRECTIVE` 的 `is_latest` 語意不受影響**（brief 要求的查核點）：
  `directive` 在 `_run_turn` 的**開跑前**就算好並存進區域變數（`ws.py` 的
  `directive = "" if in_flight.is_latest(turn_id) else _LATE_REPLY_DIRECTIVE`），
  之後只被 `turn_directive(directive)` 讀取，不會在解除之後重新查一次 `is_latest`。
  提早解除只影響**後續輪**看到的 `_order`，而那正是要修的東西。

### 🟠 Important 2：`is_last` 無人消費（commit `03f3db4`）

依裁決「保留終止訊框、改文字」。三處（`ws.py` 模組 docstring、`docs/dev/06` §5、
`docs/dev/07` channels 列）改為誠實描述：`is_last` 是協定欄位、目前的網頁客戶端不讀它、
回到待機由播放佇列排空驅動、終止訊框存在是為了未來的客戶端。
三處另加一句「**不要**改成讓前端去消費它」——否則「回到待機」會變成兩個來源說了算，
兩者不同調時長輩卡在「說話中」。

### 🟠 Important 3：`tts_chunks` 是不是孤兒 root trace（commit `03f3db4`）

**結論：是。審查員的推測成立，設計 §5.5 的宣稱不成立。** 見下節 §3。

### 次要四項

| # | 項目 | 處置 | commit |
|---|---|---|---|
| 1 | `docs/dev/17` §6「最多留兩則」 | 改「最多留兩輪」＋說明為什麼單位是輪 | `03f3db4` |
| 2 | `talkSocket.ts` 註解提到已移除的續拉 | 兩處都改（`:238` 與同一區塊上方的「含分段續拉的整套邏輯」） | `03f3db4` |
| 3 | `if tts is None: return` 連終止訊框都不送 | **讓它也送終止訊框**（`chunks = split_for_speech(...) if tts is not None else []`）——協定承諾不該因少注入一個依賴而破例 | `2c178d5` |
| 4 | 續段迴圈只接 `TTSError` | 整段包一層 try，任何例外只 `logger.exception`——續段炸掉不該把已送出的前半段打成錯誤 | `2c178d5` |

⚠️ 次要 3 有一個**行為外溢**（已寫進 commit IMPACT）：沒注入 `tts` 的測試組裝現在也會收到
終止訊框，`test_too_many_concurrent_turns_gets_a_busy_reply_not_silence` 因此改收 6 個訊框
再依 type 過濾（三輪的訊框會交錯抵達，不能假設成對出現）。這使該測試的訊框序列**與正式環境
一致了**。正式環境 `tts` 恆非 None，行為不變。

---

## 2. 「修好之前確認會紅」的證據

方法：把修好的那一行**單獨變異回修前的樣子**，跑新測試，確認紅；再還原。
（原始檔備份於 scratchpad，還原後以 `git diff --stat` 核對行數一致。）

### Critical 1

變異：`_push_continuation_chunks(sender, outcome.reply_text if outcome else "", turn_id)`
→ `_push_continuation_chunks(sender, collector.text, turn_id)`

```
$ uv run pytest tests/test_channels_app_ws.py::test_chunks_come_from_the_real_reply_not_the_debug_display_string -v

>       assert [c["text"] for c in chunks] == split_for_speech(_MULTI_SENTENCE_REPLY)[1:]
E       AssertionError: assert ['回復：第一句話夠長可以...句話也夠長可以自成一段。'] == ['第二句話也夠長可以自成..., '第三句話同樣夠長。']
E         At index 0 diff: '回復：第一句話夠長可以自成一段。' != '第二句話也夠長可以自成一段。'
E         Full diff:
E           [
E         +     '回復：第一句話夠長可以自成一段。',
E               '第二句話也夠長可以自成一段。',
E         -     '第三句話同樣夠長。',
E           ]

1 failed
```

⭐ **紅出來的內容就是審查員描述的症狀本身**：第一句被當成續段再唸一次，而且「回復：」
被 TTS 唸出來。這條測試是全庫第一條在 `show_transcript=True` 下跑的續段測試。

⚠️ 這條測試另有一行前置斷言 `assert reply["text"].startswith("辨識：")`，用來證明它真的踩
在那個分岔上——沒有這一行，`show_transcript` 若被忽略也會照樣全綠（那正是原本八輪審查漏掉
的形狀）。

### Critical 2（兩條）

變異：`if (canTakeOverSubtitle && frame.text)` → `if (canTakeOverSubtitle)`

```
$ npx vitest run src/elder/useTalk.test.ts -t "終止訊框"
 FAIL  終止訊框不可以把字幕清空（短回覆：答案剛顯示就被抹掉）
AssertionError: expected '' to be '今天天氣很好' // Object.is equality
 ❯ src/elder/useTalk.test.ts:1265:45

$ npx vitest run src/elder/useTalk.test.ts -t "續段合成失敗時"
 FAIL  續段合成失敗時，長輩至少還看得到已經送到的那一段字
AssertionError: expected '' to be '第二句。'
 ❯ src/elder/useTalk.test.ts:1307:45
```

⚠️ 依 brief 指示，既有那條「空音檔的終止訊框不進播放佇列」測試的 `emit` 已補包 `act()`
並加註解說明為什麼——它讀的是還沒沖出來的舊狀態，任何**狀態**層面的副作用都會被它悄悄放過。
不補的話下一個人會以為那條測試已經守住了狀態面。

### Important 1

變異：拿掉續段迴圈之前那行 `in_flight.finish(turn_id)`（只留 `finally` 那一行）

```
$ uv run pytest tests/test_channels_app_ws.py::test_a_turn_leaves_the_in_flight_list_once_its_answer_is_out -v
E   AssertionError: 第一輪的答案已經送出去了，卻還掛在在途清單上
tests/test_channels_app_ws.py:889: AssertionError
1 failed
```

該測試**以事件（不是 sleep）**把「A 正在推續段」釘死在 B 組裝情境的當下：router 層的續段
TTS 第一次合成就 `Event.wait()` 卡住，確認 `entered` 之後才送第二輪。

---

## 3. Important 3：我查到什麼

分兩步，**先讀原始碼、再上真的 Opik 實測**。

**第一步（原始碼）**：`kinsun/tracing/decorators.py::track` 只是 lazy 包一層 `opik.track`，
沒有自己的 parent 邏輯。`opik/decorator/span_creation_handler.py::create_span_respecting_context`
的最後一個分支寫得很明白：

```python
if current_span_data is None and current_trace_data is None:
    # Create a trace and root span because it is
    # the first decorated function run in the current context.
    current_trace_data = trace.TraceData(...)
```

而 `_push_continuation_chunks` 在 `dispatch(...)` **回傳之後**才被呼叫，那時
`care_conversation`（trace root）與 `care_turn_voice` 都已關閉、context storage 已被
`pop_span_data()`／`pop_trace_data()` 清空。

**第二步（實測）**：本機自架 Opik（`localhost:5273`，確認可達）開一個獨立專案，照
`ws.py::_run_turn` 的真實結構跑一輪——外層 `care_conversation` 內含 `care_turn_voice`
先跑完並**回傳**，之後才呼叫 `tts_chunks`——`opik.flush_tracker()` 後查
`GET /api/v1/private/traces`：

```
專案 kinsun-orphan-probe-1785584315 的 root trace 共 2 棵：['care_conversation', 'tts_chunks']
```

**裁決**：設計 §5.5 的「續段的耗時改由 `care_turn_voice` 這棵樹涵蓋，順帶修掉孤兒 root
trace 那個既有問題的另一半」**不成立**。孤兒 trace 沒被修掉，**形態改變了**——舊的是「每次
REST 續拉一棵」（審查員實測 n=57），新的是「**每一輪一棵**」，而每輪都有續段，所以總量可能
更高。

**處置**（依指示未改變呼叫點位置）：
- 設計文件 §5.5 改寫為誠實描述，含原始碼依據、實測方法與結果、以及「真正要修需要什麼」。
- `ws.py` 的 `@tracing.track(name="tts_chunks")` 上方補註解記載同一件事，並明寫
  **不要為了修它而搬動呼叫點**——那個位置同時承載 D-2（續段留在容量閘門之內）與
  Important 1（在途清單在續段之前解除）兩項約束。

---

## 4. 測試指令與輸出摘要

| 指令 | 結果 |
|---|---|
| `uv run pytest -q`（全庫、單行程循序） | **2719 passed**（含他人未提交的 RAG 工作；本批範圍為 `test_channels_app_ws.py` 47 條、`test_channels_inbound.py` 36 條） |
| `uv run pytest tests/test_channels_app_ws.py -q` | 47 passed（本批 +2） |
| `uv run ruff check src tests` | All checks passed |
| `uv run ruff format --check`（本批檔案） | 16 files already formatted |
| `npm test`（`web/`） | **587 passed**（41 檔，本批 +2） |
| `npm run typecheck` | 乾淨 |
| `npm run lint` | 乾淨 |

每顆 commit 落地前都單獨跑過其範圍內的測試，確認**每一顆都可獨立 review、獨立 revert**：
`20b81f5` 後 `test_channels_app_ws.py`＋`test_channels_inbound.py` 83 passed；
`2c178d5` 後 `test_channels_app_ws.py` 47 passed＋ruff 乾淨。

---

## 5. commit 切分

| commit | 範圍 |
|---|---|
| `20b81f5` `fix(ws)` | Critical 1：`DeliveryOutcome.reply_text`＋呼叫點＋兩條測試 |
| `fad52c3` `fix(web)` | Critical 2：字幕空字串守門＋兩條測試＋既有測試補 `act()` |
| `2c178d5` `fix(ws)` | Important 1＋次要 3／4：在途清單提早解除、續段例外隔離、終止訊框恆送 |
| `03f3db4` `docs` | Important 2／3＋次要 1／2：三處 `is_last` 誠實化、§5.5 依實測更正、17 補播單位、`talkSocket.ts` 註解 |

`ws.py` 的改動橫跨三顆 commit，以逐 hunk 拆分（含把「在途清單解除」與「呼叫點換文字來源」
這兩個相距三行的變更拆成獨立 sub-hunk）分批落地，而非把整個檔案塞進一顆。

文件版頭與狀態表已同步：`docs/dev/06` v1.28→**v1.29**、`07` v2.01→**v2.02**、
`17` v1.33→**v1.34**，`docs/dev/README.md` 對應三列同步。

---

## 6. 疑慮

1. **⚠️ 孤兒 root trace 的形態改變，而這一波不修。** 舊：每次 REST 續拉一棵；新：**每一輪一棵**，
   且每一輪都有續段。形態改變導致總量未測（短回覆現在多一棵、長回覆則無變化），Opik 的
   專案視圖會被 `tts_chunks` 洗版，`care_conversation` 的「一輪＝一棵樹」直覺不再成立，
   查問題的人要自己在兩棵樹之間對時間。這是**已知且刻意接受**的退步，理由是修它要動呼叫點、
   而呼叫點承載兩項約束。若畢典前要看 Opik 追延遲，建議先在 UI 上以名稱過濾。

2. **在途清單提早解除，長輩「連續插嘴」時的名額語意變了。** `_MAX_CONCURRENT_TURNS=3` 現在
   算的是「還沒把答案送出去的輪」，不含「正在推續段的輪」。這正是 Important 1 要的，但副作用
   是**同時打 GPU 的輪數可能比 `in_flight` 顯示的多**（續段仍在跑卻已不在清單裡）。
   真正擋 GPU 的是 `TurnAdmission`（續段仍在它之內），所以安全，但**若有人日後拿
   `in_flight` 的長度當負載指標，那個數字現在會低估**。已寫進程式碼註解。

3. **Critical 2 的兩條新測試都是「同步時序」的模擬。** 它們用 `act()` 逐一沖狀態，重現的是
   「終止訊框緊接在 reply 之後抵達」。真實瀏覽器裡 `queue.push` 是否**一定**同步跑完播放
   回呼（審查員論證的關鍵一步），我沒有在真瀏覽器上驗證——但這不影響修法的正確性：不論同步
   與否，空字串都不該蓋掉字幕。

4. **`test_a_turn_leaves_the_in_flight_list_once_its_answer_is_out` 用了 `timeout=5` 的
   事件等待與一個 500×10ms 的輪詢。** 在極慢的機器上理論上可能偽紅（會以自訂訊息指出
   「第二輪沒有組裝情境」而非靜默掛住）。帳本 Task 3 已列「`_frames`／`_receive_frame`
   無內建逾時」為待查項，這條測試同屬該類，一併留給 pytest-timeout 的決策。

5. **這一波沒有做人工／實機驗收。** 兩個 Critical 的修正都影響長輩實際聽到與看到的東西，
   建議在 `ASR_DEBUG_SHOW_TRANSCRIPT=true`（現值）下實機跑一輪長回覆，確認：
   ①續段不再重播第一句、不再唸出「回復：」；②短回覆答完之後字幕**留在畫面上**。

6. **工作區有他人未提交的 RAG 改動**（`rag/crawler.py`、`rag/content_filter.py`、
   `rag/ingestion.py` 等十餘檔，其中數檔在本次工作期間才出現變更）。我**完全沒有碰**它們，
   四顆 commit 皆以明確路徑 `git add`，未使用 `git add -A`。全庫 pytest 的 2719 條包含那些
   改動帶進來的測試，故與帳本記載的 2690 不可直接相比；本批自身淨增 4 條（後端 2、前端 2）。

---

## 7. 追記：交付前的獨立覆核（2026-08-01 20:10）

本節由**同一批任務的另一個並行 session** 在交付前重跑一次驗證後補上。兩個 session
共用同一個工作區，收斂到同一組修法（`DeliveryOutcome.reply_text`、`frame.text` 守門、
`in_flight` 前移、續段迴圈自帶 try、終止訊框恆送），上表四顆 commit 即最終結果。
以下三點與上文所載略有出入，以本節為準：

### 7.1 追加一顆 commit：`ff3c0d4 style(ws)`

`037123d`（在途清單註解的措辭修正）留下一行 101 字元的註解，`uv run ruff check src tests`
在 HEAD 上因此是紅的。已把該行句尾的 `` `pending_utterances` `` 改寫成同義的「在途清單」
把行長壓回上限內。**零行為改變**，註解陳述的事實一字未變。

### 7.2 全庫 pytest 的實際數字

| 指令 | 本次覆核結果 |
|---|---|
| `uv run pytest -q`（全庫、單行程） | **2698 passed / 6 failed** |
| `uv run pytest tests/test_channels_app_ws.py -q` | 47 passed |
| `uv run pytest tests/test_channels_inbound.py -q` | 37 passed |
| `npm test`（`web/`，41 檔） | 587 passed |
| `npm run typecheck`／`npm run lint` | 乾淨 |
| `uv run ruff check src tests` | 本批檔案無錯誤（餘 4 筆 F821 見 7.3） |

⚠️ 6 條紅燈全部落在 `tests/test_pg_rag_releases.py`，**與本批無關**，證據：
該檔在工作區是**未提交**狀態，其未提交版本第 55／155 行改成
`SourceRegistry().get("hpa_health_education")`，而 `source_registry.py`（同樣未提交、
同一位組員的在途工作）目前還沒有這個 source id，故拋 `KeyError`；HEAD 版該檔用的是
`hpa_elder_health`。同理，`ruff` 剩下的 4 筆 `F821` 全在 `src/kinsun/rag/refresh.py`
（亦為未提交的在途工作）。上文 §4 記的「2719 passed」是更早一個時點的快照，該組員
其後又改動了 RAG 檔案，故數字對不上——**本批範圍內的測試兩次都是全綠**。

### 7.3 分支上出現他人的 commit

覆核期間 `Leo` 分支多了 `fe66862`／`6fbe293` 兩顆 RAG commit（另一位組員）。本批的
六顆（`20b81f5`／`fad52c3`／`2c178d5`／`03f3db4`／`037123d`／`ff3c0d4`）與它們互不重疊，
每一顆都只以明確路徑 `git add`。⚠️ 交由整合負責人開 PR 時請注意：這條分支上同時躺著
兩批不同主題的工作，且 RAG 那批仍有大量未提交檔案。

### 7.4 仍然成立的最大疑慮

§6 的六項照舊，其中第 5 項（**沒有做人工／實機驗收**）在覆核後份量更重：兩個 Critical
改的都是長輩實際聽到與看到的東西，而這台機器的 `.env` 現值就是
`ASR_DEBUG_SHOW_TRANSCRIPT=true`——Critical 1 的發作條件現在就滿足。建議合併前實機跑
一輪長回覆確認：①續段不再重播第一句、不再唸出「回復：」；②短回覆答完之後字幕留在畫面上。
