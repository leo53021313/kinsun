# 設計：新增取得目前時間工具 ＋ 天氣先問地點

日期：2026-07-03
分支：Leo
狀態：待實作

## 背景與目標

`src/kinsun/tools/` 目前有 `weather`（Open-Meteo 天氣）與 `health_rag`（衛教 RAG）兩個工具。本次需求：

1. **新增「取得目前時間」工具**：長輩問「現在幾點／今天幾號／今天星期幾」時，金孫能回答台灣時間。
2. **天氣要有地點才準**：天氣工具在不知道長輩所在城市時，應「先問」而非自行假設（例如預設台北）。

## 關鍵現況（決定設計）

- 工具 handler 是**無狀態**的：`ToolRegistry.dispatch(name, arguments)`（`tools/registry.py`）只把 LLM 給的 `args` 傳進 handler，**拿不到「當前是哪位長輩」**。
- `Elder` 模型（`accounts/models.py`）**沒有地點欄位**，系統沒有任何長輩所在地資料。
- 因此「自動取得長輩存檔地點」需動 DB schema ＋ 把長輩身分接進 dispatch 契約，屬較大變更。
- 既有工具工廠模式：`build_weather_handler(fetch_json=...)`，依賴以參數注入、利於測試。
- LLM 層以 `parameters_json_schema=t.parameters` 轉成 Gemini FunctionDeclaration（`llm.py`），無參數工具用空 `properties` 是合法 JSON Schema。

## 決策

天氣地點策略採 **「先問」（最小改動）**：只改工具描述與系統提示，**不動 DB、不動 dispatch 契約**。
（已排除「幫長輩存城市」方案：需不可逆 schema 變更與工具契約改動，範圍過大，本次不做。）

## 設計

### 任務 1：`get_current_time` 工具（新增）

- **新檔** `src/kinsun/tools/clock.py`（刻意不用 `time.py`／`datetime.py`，避免遮蔽 stdlib）。
- `CURRENT_TIME_SPEC`：
  - `name = "get_current_time"`
  - `description`：長輩問現在幾點、今天幾號、今天星期幾時使用；回台灣時間。
  - `parameters = {"type": "object", "properties": {}}`（無參數）。
- `build_current_time_handler(now: Callable[[], datetime]) -> Callable[[dict], str]`：
  - 比照 weather 的工廠模式，`now` 可注入以利測試。
  - 回傳白話字串，例：`現在是 2026年7月3日 星期四，下午2點30分。`
  - 星期：`weekday()`（0=一）對映 `"一二三四五六日"`。
  - 時段＋12 小時制：凌晨（0–4）／上午（5–11）／中午（12）／下午（13–17）／晚上（18–23）；`h12 = hour % 12`，為 0 時作 12。
  - 分鐘：整點講「整」，否則「N分」。
- **註冊**（`app.py`，緊接現有 weather 註冊）：
  `registry.register(CURRENT_TIME_SPEC, build_current_time_handler(lambda: datetime.now(tz)))`——沿用現成 `tz`。
- **測試** `tests/test_tools_clock.py`：注入固定 clock，驗證：
  - `CURRENT_TIME_SPEC.name == "get_current_time"`。
  - 格式含年月日、正確星期、正確時段（上午／下午等）與時分。
  - 整點會講「整」。

### 任務 2：天氣「先問地點」（只動提示）

- **收緊** `weather.py` 的 `WEATHER_SPEC.description`：只有在已確認長輩要查哪個城市時才呼叫；不知道地點就先開口問長輩人在哪個城市，**不要自行假設台北**。
- **加一句** `agent.py` 的 `SYSTEM_PROMPT`：查天氣前若不知道長輩人在哪個城市，先親口問，不要自己猜。
- 保留現有空地點防呆（`weather.py` handler 對空字串回「請告訴我您想查哪個地方」）作為第二道防線。
- 既有 `tests/test_tools_weather.py` 行為不變，應持續通過。

## 改動檔案

- 新增：`src/kinsun/tools/clock.py`、`tests/test_tools_clock.py`
- 修改：`src/kinsun/app.py`（註冊時間工具）、`src/kinsun/tools/weather.py`（description）、`src/kinsun/agent.py`（system prompt 一句）

## 驗證

1. 執行既有測試（含 weather、registry）確認未回歸。
2. 新增 `test_tools_clock.py` 單元測試通過。
3. 人工／實跑一次工具迴圈，確認無參數工具不會觸發 Gemini 400。

## 風險

- 無參數工具（空 `properties`）給 Gemini `parameters_json_schema`：理論合法，實作時實跑確認。若有問題，退路為在 schema 補一個 optional 說明性欄位或改用非空但可忽略的參數。
