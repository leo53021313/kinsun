# 排程器 cron 化與狀態持久化 設計

> 對應架構圖 [長輩看護系統架構-分層版.drawio](../../長輩看護系統架構-分層版.drawio)：⑥ 主動關懷（排程引擎 Cron）。
> 前置模組：[排程引擎](2026-06-29-排程引擎-design.md)、[主動關懷](2026-06-29-主動關懷-design.md)、[記憶層雲端遷移](2026-06-29-記憶層雲端遷移-design.md)。
> 借鏡來源：hermes-agent `cron/`（狀態落盤、以 last_run 為基準算 next_run、補跨一次；本機 `temp/` 參考、不進版控）。
> 本案為「Hermes / Mem0 借鏡與優化」系列第 2 項（T2.3）。

---

## 1. 背景與目標

現行 [Scheduler](../../../src/kinsun/scheduler/scheduler.py) 的 `_last_run: dict[str, date]` 為**純記憶體**：worker 一重啟即清空 → 當天已發過的早安／失聯關心會**重複發送**（對長輩體驗傷害大）。排程比較用 `(now.hour, now.minute) >= (job.hour, job.minute)` 也有跨日邊界風險，且只支援「每天某時一次」。

本案把排程器升級為：
1. **狀態持久化**：`last_run` 落 Postgres，worker 重啟讀回 → 不重發。
2. **完整 cron 排程**：`Job` 改帶 cron 字串，以 `croniter` 解析（取代 hour/minute tuple 比較）。
3. **補跨一次（catch-up once）**：以 `last_run` 為 croniter 基準算 `next_fire`；停機跨過觸發 → 重啟補跑一次後快進，不洪水重播。

**完成後：** worker 重啟不再重複發訊息；排程支援任意 cron；停機後最多補一則稍晚訊息。內建三個 job（整理／問候／失聯關心）行為不變（仍每天某時），但底層走 cron。

---

## 2. 範圍（Scope）

### 2.1 在範圍內
* `Job` 資料結構：`(name, hour, minute, run)` → `(name, cron, run)`。
* `ScheduleStateStore` Protocol + `PgScheduleStateStore`（Postgres）+ `FakeScheduleStateStore`（測試）。
* `Scheduler` 改注入 `ScheduleStateStore`，`_is_due` 以 croniter + last_run 實作補跨一次；`run_due` 三段 fail-safe 保護。
* job builders（`build_consolidation_job` / `build_greeting_job` / `build_inactivity_job`）：**維持收 `hour`/`minute` 參數**，內部轉成 cron 字串 `f"{minute} {hour} * * *"`。
* `db.py`：新增 `scheduler_state` 表 DDL，併入 `ensure_schema`。
* `worker.py`：`build_scheduler` 注入 `PgScheduleStateStore(url, tz)`。
* `pyproject.toml`：新增依賴 `croniter`（純 Python，linux/aarch64 有通用 wheel）。
* 相應測試：重寫 `test_scheduler.py`（新語意）、更新 `test_scheduler_jobs.py`（`job.hour`→`job.cron`）、新增 `PgScheduleStateStore` round-trip（opt-in）。

### 2.2 不在範圍內（YAGNI／後續）
* **env 字串自訂任意 cron job**（job 設定系統）；內建 3 job 仍由 env 時數轉 cron，新 cron job 於程式碼定義。
* **grace window**（停機太久就跳過）；本案一律補跨一次。
* 多機鎖、外部排程提供者、delivery 系統（hermes 有，對單機小專案過重）。
* 更動 env 介面（`CONSOLIDATION_HOUR` 等保留不變）。

---

## 3. 排程邏輯（cron + 補跨一次）

```python
def _is_due(self, job, now) -> bool:
    last = self._state.get_last_run(job.name)
    if last is None:                       # 首見：種基準，下一次 cron 時間才觸發
        self._state.set_last_run(job.name, now)
        return False
    next_fire = croniter(job.cron, last).get_next(datetime)
    return next_fire <= now
```

* **首見種基準**：部署當下不立即亂發；部署於該日 cron 時間「之前」仍會當天觸發、「之後」則跳到下一次。
* **補跨一次**：`croniter(cron, last).get_next()` 只取「last 之後的第一個」觸發；跑完 `set_last_run(now)` → 直接快進。故無論停機跨過幾次，最多補一次。
* **croniter**：`croniter(expr, start_aware_dt).get_next(datetime)` 回傳同 tz 的 aware datetime；與 `now`（`datetime.now(tz)`）直接比較。Asia/Taipei 無 DST，無時刻歧義。

`run_due` 改為三段獨立保護（fail-safe）：

```python
def run_due(self) -> list[str]:
    now = self._clock()
    ran = []
    for job in self._jobs:
        try:
            due = self._is_due(job, now)
        except Exception:                       # 狀態讀取失敗 → 跳過此 job
            logger.exception("排程到期判斷失敗：%s", job.name)
            continue
        if not due:
            continue
        try:
            job.run()
        except Exception:                        # job 執行失敗 → 記錄但仍標記（避免每 tick 重試洗版）
            logger.exception("排程 job 失敗：%s", job.name)
        try:
            self._state.set_last_run(job.name, now)
        except Exception:
            logger.exception("排程狀態寫入失敗：%s", job.name)
        ran.append(job.name)
    return ran
```

> 「即使 job 失敗也標記 last_run」沿用現行語意（每日至多一次，失敗不每 tick 重試）。代價：當天失敗不重試（隔日再來）。

---

## 4. 元件與介面

### 4.1 狀態儲存（scheduler/state.py，新檔）

```python
class ScheduleStateStore(Protocol):
    def get_last_run(self, job_name: str) -> datetime | None: ...
    def set_last_run(self, job_name: str, when: datetime) -> None: ...

class PgScheduleStateStore:
    def __init__(self, database_url: str, tz: tzinfo) -> None: ...
    # get：SELECT last_run_at WHERE job_name=%s → datetime.fromtimestamp(ts, tz) 或 None
    # set：INSERT ... ON CONFLICT (job_name) DO UPDATE SET last_run_at=%s（when.timestamp()）
```

* `tz` 用於把存的 epoch（`DOUBLE PRECISION`）還原成 aware datetime（croniter 需 aware）。
* DB 失敗拋自有例外（沿用 `MemoryError` 風格的 `ScheduleStateError`），由 `run_due` 各段 try 吞掉。
* `FakeScheduleStateStore`（tests/fakes.py）：記憶體 `dict[str, datetime]`，直接存還 aware datetime。

### 4.2 Scheduler（scheduler/scheduler.py）

```python
@dataclass(frozen=True)
class Job:
    name: str
    cron: str
    run: Callable[[], None]

class Scheduler:
    def __init__(self, jobs: list[Job], clock: Callable[[], datetime],
                 state: ScheduleStateStore) -> None: ...
```

### 4.3 job builders（scheduler/jobs.py、proactive/jobs.py）

簽名**不變**（仍 `hour`, `minute=0`），內部產生 cron：

```python
def build_consolidation_job(*, sessions, run_one, hour, minute=0,
                            name="daily-consolidation") -> Job:
    cron = f"{minute} {hour} * * *"
    def run() -> None: ...   # 同現行
    return Job(name=name, cron=cron, run=run)
```

`build_greeting_job` / `build_inactivity_job` 同理（內部行為不變，只改建構的 Job）。

### 4.4 建表（db.py）

```python
SCHEDULER_DDL = (
    "CREATE TABLE IF NOT EXISTS scheduler_state ("
    "job_name TEXT PRIMARY KEY, last_run_at DOUBLE PRECISION NOT NULL);"
)
# ensure_schema 內：conn.execute(SCHEDULER_DDL)
```

### 4.5 組裝（worker.py）

```python
state = PgScheduleStateStore(settings.database_url, tz)
...
return Scheduler(jobs, clock, state)
```

env 時數照舊傳給 builders（`hour=settings.greeting_hour` 等）。無新環境變數。

---

## 5. 錯誤處理（fail-safe）

* `run_due` 三段（is_due／run／set_last_run）各自 try/except，單 job 任一段失敗只記錄、不影響其他 job、不崩潰 worker 迴圈。
* `set_last_run` 在 `job.run()` 之後即使 run 失敗也執行 → 失敗 job 當天不重試洗版。
* run 成功但 set_last_run 失敗（罕見）→ 下一 tick 可能重發一次；屬可接受 fail-safe 邊界，已記錄。
* secret 全走環境變數；SQL 全參數化。

---

## 6. 測試策略（單元全離線，Pg round-trip opt-in）

* **`tests/test_scheduler.py`（重寫，注入 `FakeScheduleStateStore` + 假 clock）：**
  * 首見種基準：fresh job 第一次 tick 不觸發、`get_last_run` 被種值。
  * 到點觸發：種基準後 now 跨過 cron 時間 → 觸發一次。
  * 當日不重觸發：觸發後同日再 `run_due` → `[]`。
  * **重啟不重跑（核心 bug 修復證明）**：同一 `FakeScheduleStateStore` 餵給新建的 `Scheduler` → 當天不重發。
  * **補跨一次**：先設 `last_run`=昨日觸發時刻，now=今日已過觸發 → 觸發一次；緊接再 `run_due` → `[]`（已快進）。
  * 完整 cron：`*/5 * * * *` 在跨過 5 分鐘界時觸發。
  * 單 job 失敗隔離：run 拋例外 → 其餘照跑、該 job 仍在 `ran`、仍標記 last_run。
* **`tests/test_scheduler_jobs.py`：** `job.hour == 3` → `job.cron == "0 3 * * *"`。
* **`tests/test_proactive_jobs.py`：** 不動（仍以 `hour=` 建 job、直接 `.run()`；不碰 Scheduler）。
* **`PgScheduleStateStore` round-trip（`KINSUN_IT=1`）：** set→get 還原 aware datetime；無資料回 None。

---

## 7. 已知取捨（列出供否決）

* **首見不立即觸發**：部署當下不亂發、語意乾淨；代價是部署於當日 cron 時間之後 → 當天那次跳過（隔日起正常）。
* **補跨一次、無 grace window**：簡單；代價是停機很久後仍補一則稍晚訊息（至多一則）。
* **失敗也標記 last_run**：避免每 tick 重試洗版；代價是當天失敗不自動重試。
* **builders 維持收 hour/minute**：worker 與 env 介面零變更；代價是「任意 cron job」需改程式碼（非 env 設定）。
* **新增 croniter 依賴**：完整 cron 解析手刻易錯，croniter 純 Python、ARM64 相容，屬「充分理由」。
