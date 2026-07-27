"""全系統排程宣告的唯一真實來源：有哪些 job、何時跑、誰負責跑。

⚠️ 為什麼需要這個檔（2026-07-27）：排程跑在**兩個程序**——主排程器
（`python -m kinsun.cron`）與 RAG 週更（`python -m kinsun.rag.worker`）。在此檔
出現之前，兩邊各自宣告自己的 job，而後台 `GET /admin/jobs` 只拿得到主排程器
那一份。於是 `rag-weekly-refresh` 對那一頁**完全不存在**：rag_worker 掛掉、
`RAG_REFRESH_ENABLED` 忘了打開、從部署起一次都沒跑過，那一頁一律顯示全綠。

而那一頁正是 2026-07-26「排程器活著但停擺七小時」事故之後才建的，存在的唯一
理由就是抓這種事。它抓不到自己視野外的程序——所以視野必須先變成全系統的。

**新增或調整排程時只改這裡。** 兩個程序各自依 `owner` 挑出自己要跑的，名單對不上
會被 `test_cron_registry.py` 擋下來，也會在 `build_jobs` 啟動時就拋例外。
"""

from __future__ import annotations

from dataclasses import dataclass

from kinsun.config import Settings

OWNER_SCHEDULER = "scheduler"
"""由主排程器執行：`python -m kinsun.cron`（正式環境為 kinsun-scheduler.service）。"""

OWNER_RAG_WORKER = "rag_worker"
"""由 RAG 週更程序執行：`python -m kinsun.rag.worker`。

⚠️ 為什麼不併回主排程器：RAG 週更只需要 DB 與 Gemini 金鑰，刻意用
`RagWorkerSettings` 這份最小設定啟動——併回去會讓它在 LINE、LIFF、語音任一
金鑰漏設時跟著起不來（見 `config.RagWorkerSettings` 與 docs/dev/14）。
拆是對的；錯的是拆完之後沒有人統一看得到它，那由本檔修正。
"""

# 自適應問候的掃描頻率：每半小時掃一次，過了她的偏好時間且今天還沒問候過才送。
# ⚠️ 改這個值會連動 `proactive/constants.py` 的偏好時間對齊規則——偏好時間只會落在
# 這份 cron 掃得到的時刻上，改成每小時掃，所有存成 xx:30 的偏好都會晚半小時到一小時。
GREETING_SCAN_CRON = "0,30 * * * *"

# 統一排程派送（D-76 P2）：時刻是每位長輩、每筆排程各自設定的，沒有共用鐘點可掛，
# 只能每分鐘掃。
SCHEDULE_DISPATCH_CRON = "* * * * *"


@dataclass(frozen=True)
class JobSpec:
    """一支排程的宣告。這裡只講「什麼時候、誰跑」，不含要跑的程式本身。"""

    name: str
    cron: str
    owner: str
    max_lateness_seconds: float | None = None
    """遲到多久就算「已經造成損害」；`None` ＝ 用後台的預設容許量。見 `Job` 同名欄位。"""

    background: bool = False
    """長跑 job：丟到獨立執行緒，不佔住掃描迴圈。見 `Job.background`。

    ⚠️ 判準是「它的耗時會不會隨長輩人數成長」——會遍歷全部長輩且逐位呼叫 LLM 的
    才要標。清理類的幾句 SQL 跑得比一次掃描還快，標了只是多開執行緒。
    """


def _daily(hour: int, minute: int) -> str:
    return f"{minute} {hour} * * *"


def rag_refresh_spec(*, cron: str) -> JobSpec:
    """RAG 週更的宣告。

    獨立成函式是因為它的兩個消費端拿到的設定型別不同：後台與主排程器讀 `Settings`，
    RAG Worker 讀 `RagWorkerSettings`（最小設定）。兩者的 `RAG_REFRESH_CRON` 是同一個
    環境變數，但 job 名稱只能有一份——名稱對不上，後台就會把它當成「從未執行」。
    """
    return JobSpec(name="rag-weekly-refresh", cron=cron, owner=OWNER_RAG_WORKER)


def job_specs(settings: Settings) -> list[JobSpec]:
    """本組設定下**全系統**會存在的排程，跨程序。

    含條件註冊的 job：設定沒開就不在清單裡，後台因此不會把「刻意沒啟用」誤報成
    「從未執行」。
    """
    nightly = settings.longterm_consolidation_hour
    specs = [
        # 夜間批次：整理→摘要→反思→問候時間，逐位長輩跑。xx:05 執行——「昨日對話
        # 短長期兩不著」的凌晨盲窗由三小時縮到 5 分鐘（✅ 庚-48／A-21）。
        JobSpec("daily-consolidation", _daily(nightly, 5), OWNER_SCHEDULER, background=True),
        JobSpec("daily-greeting", GREETING_SCAN_CRON, OWNER_SCHEDULER, background=True),
        JobSpec(
            "inactivity-care",
            _daily(settings.proactive_inactivity_hour, 0),
            OWNER_SCHEDULER,
            background=True,
        ),
        JobSpec(
            "schedule-dispatch",
            SCHEDULE_DISPATCH_CRON,
            OWNER_SCHEDULER,
            # 遲到超過判定窗＝這段時間該送的提醒**已經永久遺失**（窗外一律作廢不補）。
            # 後台的預設容許量 300 秒遠大於這個窗，沿用會在提醒已經掉了時還顯示健康。
            max_lateness_seconds=float(settings.schedule_dispatch_window_seconds),
        ),
    ]
    # 音檔清理僅在 AUDIO_RETENTION_DAYS>0 時註冊（0＝音檔本體不刪，2026-07-09 修訂）。
    if settings.tts_backend == "dgx" and settings.audio_retention_days > 0:
        specs.append(JobSpec("audio-cleanup", _daily(nightly, 30), OWNER_SCHEDULER))
    # 進站音檔與 TTS 音檔同樣走過期清理；有 Supabase 憑證且 retention>0 才啟用。
    has_storage = bool(settings.supabase_url and settings.supabase_service_key)
    if has_storage and settings.audio_retention_days > 0:
        specs.append(JobSpec("inbound-audio-cleanup", _daily(nightly, 30), OWNER_SCHEDULER))
    specs.append(JobSpec("observability-cleanup", _daily(nightly, 45), OWNER_SCHEDULER))
    # 話題新聞（spec 2026-07-20）：跑在夜間批次同一個鐘點、錯開分鐘，讓早上問候時
    # 已有當天的新聞可用。
    specs.append(JobSpec("news-crawl", _daily(nightly, 15), OWNER_SCHEDULER))
    specs.append(JobSpec("news-cleanup", _daily(nightly, 50), OWNER_SCHEDULER))
    if settings.rag_refresh_enabled:
        specs.append(rag_refresh_spec(cron=settings.rag_refresh_cron))
    return specs
