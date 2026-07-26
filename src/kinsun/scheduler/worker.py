"""排程 worker：長跑迴圈，定時 run_due。

CLI：PYTHONPATH=src uv run python -m kinsun.scheduler
"""

from __future__ import annotations

import faulthandler
import logging
import os
import signal
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from kinsun import tracing
from kinsun.accounts.models import PrincipalType
from kinsun.agent import Recall
from kinsun.audio.publisher import build_audio_publisher
from kinsun.composition import Core, assemble_core, build_externals
from kinsun.config import Settings, load_dotenv, load_settings
from kinsun.db import Database
from kinsun.llm import build_gemini_for
from kinsun.memory.longterm.consolidation import run_consolidation
from kinsun.memory.longterm.consolidation_log import PgConsolidationLogStore
from kinsun.news.fetchers.mohw import MohwNewsFetcher
from kinsun.news.fetchers.news_api import NewsApiFetcher
from kinsun.news.fetchers.protocol import NewsFetcher
from kinsun.news.fetchers.rss import RssNewsFetcher
from kinsun.news.jobs import build_news_cleanup_job, build_news_crawl_job
from kinsun.observability.jobs import build_observability_cleanup_job
from kinsun.proactive.greeting_time import update_greeting_time
from kinsun.proactive.jobs import (
    INACTIVITY_INTENT,
    build_greeting_job,
    build_inactivity_job,
    greeting_intent,
)
from kinsun.reports.reminders import (
    REMINDER_KIND_PROACTIVE_CARE,
    REMINDER_KIND_PROACTIVE_GREETING,
    safe_record,
)
from kinsun.reports.summaries import summarize_day
from kinsun.scheduler.jobs import build_audio_cleanup_job, build_consolidation_job
from kinsun.scheduler.scheduler import Job, Scheduler
from kinsun.scheduler.state import PgScheduleStateStore
from kinsun.schedules.jobs import build_schedule_dispatch_job
from kinsun.strategies.reflection import reflect_days

logger = logging.getLogger("kinsun.scheduler.worker")

# 會遍歷全部長輩、且逐位呼叫 LLM 的 job；改由獨立執行緒跑，不佔住掃描迴圈。
# ⚠️ 新增這類 job 時要記得列進來——判準是「它的耗時會不會隨長輩人數成長」。
# 2026-07-26 實測：39 位長輩的夜間批次讓每分鐘的 `schedule-dispatch` 停了兩分鐘。
_LONG_RUNNING_JOBS = frozenset({"daily-consolidation", "daily-greeting", "inactivity-care"})


def build_jobs(settings: Settings, core: Core, *, clock: Callable[[], datetime]) -> list[Job]:
    """組出全部排程 job；worker 排程執行、web 端 admin 手動觸發（spec 2026-07-12）共用同一份。"""
    db = core.db
    memory = core.memory
    long_term = core.long_term
    # 摘要按用途配模型（✅ D-16 丁-5）：與主模型相同時共用連線。
    gemini = (
        core.gemini
        if settings.gemini_model_summary == settings.gemini_model
        else build_gemini_for(
            settings, settings.gemini_model_summary, client_wrapper=tracing.wrap_genai
        )
    )
    accounts = core.accounts
    reminder_logs = core.reminder_logs
    agent = core.agent
    router = core.router
    traces = core.traces
    summaries = core.summaries
    # 摘要納 L1 小訊號（✅ D-10 己-5）：worker 自組 risk_events 讀取端。
    risk_events = core.risk_events
    # 反思寫入端；與後台檢視／撤銷同一個 store（已在 Core），不另建。
    strategies = core.strategies
    # 問候偏好：夜間批次（run_one 第四步）寫、問候 job 讀，同一個 store。
    greeting_prefs = core.greeting_prefs
    # 話題新聞（spec 2026-07-20）：爬取／清除 job 寫、問候 job 讀，同一個 store。
    news = core.news
    # 整理進度標記（✅ 庚-06／庚-13）：逐日補齊＋冪等，避免停機漏天與重覆寫入。
    consolidation_log = PgConsolidationLogStore(db, clock=clock)

    def run_one(elder_id: str) -> None:
        run_consolidation(
            elder_id,
            short_term=memory,
            long_term=long_term,
            log=consolidation_log,
            now=clock(),
        )
        try:
            summarize_day(
                elder_id,
                short_term=memory,
                summarizer=gemini,
                summaries=summaries,
                clock=clock,
                risk_events=risk_events,
            )
        except Exception:  # noqa: BLE001 - 摘要失敗不影響整理與其他長輩
            # exc_info：沒有例外內容的一行 warning 查不出任何東西——每晚反思就是這樣
            # 靜默失敗六天沒人發現（2026-07-26 全流程模擬實測才抓到是 Gemini 回 400）。
            logger.warning("對話摘要失敗 elder=%s", elder_id, exc_info=True)
        # 每晚反思（spec 2026-07-14）：接在既有的夜間批次尾巴，與摘要共用
        # GEMINI_MODEL_SUMMARY 這顆模型。反思因此是每晚自動的主線行為，不需另立 cron。
        # ⚠️ 用 if 包起來、不用 `if not enabled: return`：後面還有第四步，提早 return
        # 會讓 REFLECTION_ENABLED=false 連帶關掉問候時間計算，而兩者毫無關係。
        if settings.reflection_enabled:
            try:
                reflect_days(
                    elder_id,
                    short_term=memory,
                    reminder_logs=reminder_logs,
                    strategies=strategies,
                    reflector=gemini,
                    clock=clock,
                    lookback_days=settings.reflection_lookback_days,
                    min_observed_days=settings.reflection_min_observed_days,
                    max_strategies=settings.reflection_max_strategies,
                    max_turns=settings.reflection_max_turns,
                )
            except Exception:  # noqa: BLE001 - 反思失敗不影響整理、摘要與其他長輩
                # reflect_days 對 LLM timeout／MemoryStoreError 刻意不設防（快速失敗），防線在此。
                # 少了這層，例外會沿 fanout 冒上去：本該只是「今晚少學一條」，卻會把整位長輩的
                # 夜間批次記成失敗——縱使整理與摘要其實都做完了，值班的人會查錯方向。
                logger.warning("每晚反思失敗 elder=%s", elder_id, exc_info=True)
        # 自適應問候時間（spec 2026-07-16）：純統計、不經 LLM，不需另立 cron。
        # 掛在第四步而非另開排程。**後三步**（摘要／反思／問候時間）互不拖累：各自包
        # try/except，任一失敗只記 warning，其餘照跑。整理（第一步）刻意不設防，故它
        # 失敗會中止本位長輩的整批（後三步全部跳過）並由 fanout 記一筆 ERROR——
        # Mem0 是外部服務、掛掉很寫實，值班的人看到 ERROR 該知道那晚是真的沒整理。
        if settings.proactive_greeting_adaptive_enabled:
            try:
                update_greeting_time(
                    elder_id,
                    short_term=memory,
                    prefs=greeting_prefs,
                    clock=clock,
                    default_hour=settings.proactive_greeting_hour,
                    lookback_days=settings.proactive_greeting_lookback_days,
                    min_sample_days=settings.proactive_greeting_min_sample_days,
                    earliest_hour=settings.proactive_greeting_earliest_hour,
                    latest_hour=settings.proactive_greeting_latest_hour,
                    max_shift_minutes=settings.proactive_greeting_max_shift_minutes,
                    lag_tolerance_minutes=settings.proactive_greeting_lag_tolerance_minutes,
                )
            except Exception:  # noqa: BLE001 - 問候時間計算失敗不影響整理、摘要與反思
                logger.warning("問候時間計算失敗 elder=%s", elder_id)

    def _recall(elder_id: str) -> Recall | None:
        """她上次開口那天的對話摘要，供主動推播接續話題（spec 2026-07-17）。

        以 `last_active`（她最後一則 user turn）定位是哪一天，而**不是**「今天減
        一天」——真 Gemini 探針揪出的設計錯：失聯關心的觸發條件是「≥2 天沒開口」，
        與「昨天有她的對話」互斥，照昨天讀這條路對它永遠是 None。更糟的是昨天很
        可能有金孫自己的問候（主動推播每次都寫 assistant turn），而每日摘要不分是
        誰講的——照昨天讀會拿到一份「金孫自言自語」的摘要當成她的近況。

        任一環節缺就回 None＝退回本功能之前的行為（拿 intent 當檢索關鍵字）。與問候
        偏好讀取失敗同向（proactive/jobs.py）：降級成沒有脈絡的問候，比因為一張
        報告用的表壞掉就整批長輩沒人理她好。
        """
        last = memory.last_active(elder_id)
        if last is None:
            return None  # 她從沒開口過（新長輩）
        spoke_on = datetime.fromtimestamp(last, clock().tzinfo).date()
        try:
            row = summaries.get_for_date(elder_id, spoke_on.isoformat())
        except Exception:  # noqa: BLE001 - 摘要是錦上添花，不可擋下問候
            logger.warning("摘要讀取失敗，改用無脈絡問候 elder=%s", elder_id)
            return None
        if not row:
            return None  # 那天還沒摘要（例如她今天才剛講，夜間批次尚未跑）
        return Recall(content=row.content, days_ago=(clock().date() - spoke_on).days)

    def _push_to_elder(elder_id: str, intent: str, kind: str, *, ledger: bool = False) -> None:
        # 先確認可達再生成內容（避免白花一次 LLM 呼叫）；出站由 router 依綁定通道投遞。
        if not router.has_route(PrincipalType.ELDER, elder_id):
            logger.warning("主動推播略過（長輩無任何綁定通道）elder=%s kind=%s", elder_id, kind)
            return
        content = agent.proactive(elder_id, intent, recall=_recall(elder_id))
        if ledger:
            # ledger=True ＝ 這筆 reminder_logs 不只是觀測，它就是本推播的冪等帳本
            # （目前只有問候）：先記帳再推播，記不進去就不推。
            # 用 safe_record 吞掉寫入失敗會讓 greeted_today 永遠是 false，於是從她的
            # 偏好時間起每半小時重問候一次直到當天結束（約 30 則），每則還燒一次 LLM。
            # 失敗讓它冒到 fanout ＝ 跳過本輪、30 分鐘後重試——與問候 job 已宣告的
            # 「寧可漏問候，不可重複轟炸」同向，語意上即 at-most-once。
            reminder_logs.record(elder_id, kind, content)
            delivered = router.send_text(PrincipalType.ELDER, elder_id, content)
            if not delivered:
                # send_text 逐通道吞例外、只回傳成功數，零送達不會拋。帳已經記了
                # （at-most-once：不重推），但這一則問候等於沒送出，必須可歸因——
                # 否則後台帳上顯示「已問候」而她整天沒收到，沒人知道要去查通道。
                # 各通道的根因由 router 的 logger.exception 留痕，這裡補的是結論。
                logger.warning("問候已記帳但零通道送達 elder=%s kind=%s", elder_id, kind)
            return
        router.send_text(PrincipalType.ELDER, elder_id, content)
        # 主動推播補記 reminder_logs（純觀測，失敗不影響推播）。
        safe_record(reminder_logs.record, elder_id, kind, content)

    def _elder_interests(elder_id: str) -> tuple[str, ...]:
        """問候前從長期記憶檢索她的興趣線索（Leo 2026-07-25 興趣驅動挑題）。

        興趣是錦上添花：Mem0 是外部服務、掛掉很寫實，檢索失敗一律降級成
        沒有興趣提示，不可擋下問候（與摘要／新聞讀取失敗同向）。
        """
        try:
            hits = core.long_term.search(elder_id, "興趣 嗜好 平常喜歡做的事", top_k=3)
        except Exception:  # noqa: BLE001 - 興趣提示是加分項，不可擋下問候
            logger.warning("興趣檢索失敗，改用無興趣提示問候 elder=%s", elder_id)
            return ()
        return tuple(hit.text for hit in hits if hit.text)[:3]

    def greet_one(elder_id: str) -> None:
        # ledger=True：問候的冪等靠 greeted_today 讀這張表，記帳因此是安全關鍵。
        # intent 織入今天的日期（2026-07-17 問候多樣性）＋長期記憶的興趣線索
        # （2026-07-25，供模型當 get_news 的 topic）；話題新聞本體由模型在
        # 工具迴圈中自行以 get_news 拉取（D-74 消費端），worker 不再直讀。
        _push_to_elder(
            elder_id,
            greeting_intent(clock(), interests=_elder_interests(elder_id)),
            REMINDER_KIND_PROACTIVE_GREETING,
            ledger=True,
        )

    def care_one(elder_id: str) -> None:
        _push_to_elder(elder_id, INACTIVITY_INTENT, REMINDER_KIND_PROACTIVE_CARE)

    def greeted_today(elder_id: str) -> bool:
        """今天問候過她沒有——問候 job 每半小時掃一次，冪等全靠這裡。

        查既有的 reminder_logs（問候送出時本來就會記一筆），不另立狀態表。
        窗是「今天整天」而非「到此刻為止」：後者的 end 是排他的，剛好在掃描
        當下寫入的那筆會被漏掉；而未來的紀錄本就不存在，放寬到明日零時無害。
        讀取失敗刻意讓例外冒到 fanout ＝ 跳過該長輩（寧可漏問候，不可重複轟炸）。
        """
        day_start = clock().replace(hour=0, minute=0, second=0, microsecond=0)
        logs = reminder_logs.list_for_range(
            elder_id,
            start=day_start.timestamp(),
            end=(day_start + timedelta(days=1)).timestamp(),
        )
        return any(log.kind == REMINDER_KIND_PROACTIVE_GREETING for log in logs)

    jobs = [
        build_consolidation_job(
            sessions=memory.sessions,
            run_one=run_one,
            hour=settings.longterm_consolidation_hour,
            # ✅ 庚-48（A-21）：xx:05 執行——「昨日對話短長期兩不著」的凌晨盲窗
            # 由三小時縮到 5 分鐘（短期只裝今天、長期要等整理）。
            minute=5,
        ),
        build_greeting_job(
            sessions=memory.sessions,
            greet_one=greet_one,
            default_hour=settings.proactive_greeting_hour,
            # 緊急關閉開關（spec 2026-07-16）：關掉後連讀都不讀，全體回退
            # PROACTIVE_GREETING_HOUR——只擋夜間計算會讓表裡的舊偏好繼續生效。
            prefs=greeting_prefs if settings.proactive_greeting_adaptive_enabled else None,
            greeted_today=greeted_today,
            clock=clock,
        ),
        build_inactivity_job(
            sessions=memory.sessions,
            last_active=memory.last_active,
            clock=clock,
            threshold_seconds=settings.proactive_inactivity_days * 86400,
            care_one=care_one,
            hour=settings.proactive_inactivity_hour,
        ),
    ]
    # 統一排程派送（D-76 P2）：一個每分鐘的 job 取代原本四個用藥 job ＋ 一個回診 job。
    # 頻率必須提高，因為時刻改成每位長輩、每筆排程各自設定，沒有共用鐘點可以掛 cron。
    jobs.append(
        build_schedule_dispatch_job(
            store=core.schedule_store,
            lookup_elder=accounts.get_elder,
            guardians_of=accounts.guardians_of,
            router=router,
            clock=clock,
            window_seconds=settings.schedule_dispatch_window_seconds,
            record=reminder_logs.record,
        )
    )
    # 音檔清理僅在 AUDIO_RETENTION_DAYS>0 時註冊（0＝音檔本體不刪，2026-07-09 修訂）。
    if settings.tts_backend == "dgx" and settings.audio_retention_days > 0:
        publisher = build_audio_publisher(settings, clock=clock, new_id=lambda: uuid.uuid4().hex)
        jobs.append(
            build_audio_cleanup_job(
                cleanup=lambda: publisher.cleanup(retention_days=settings.audio_retention_days),
                hour=settings.longterm_consolidation_hour,
            )
        )
    jobs.append(
        build_observability_cleanup_job(
            purge=lambda: traces.purge_older_than(
                clock().timestamp() - settings.admin_retention_days * 86400
            ),
            hour=settings.longterm_consolidation_hour,
        )
    )
    # 進站音檔與 TTS 音檔同樣走過期清理；有 Supabase 憑證且 retention>0 才啟用。
    has_storage = bool(settings.supabase_url and settings.supabase_service_key)
    if has_storage and settings.audio_retention_days > 0:
        inbound_audio = build_audio_publisher(
            settings, clock=clock, new_id=lambda: uuid.uuid4().hex, prefix="inbound"
        )
        jobs.append(
            build_audio_cleanup_job(
                cleanup=lambda: inbound_audio.cleanup(retention_days=settings.audio_retention_days),
                hour=settings.longterm_consolidation_hour,
                name="inbound-audio-cleanup",
            )
        )
    # 話題新聞（spec 2026-07-20）：衛福部與 RSS 免金鑰、一律註冊（RSS feed 清單
    # 留空＝不用）；News API 需要 NEWS_API_KEY，留空＝優雅降級。單一來源失敗不擋
    # 其他來源（news/jobs.py）。跑在夜間批次同一個鐘點、錯開分鐘，讓早上問候時
    # 已有當天的新聞可用。
    news_fetchers: list[NewsFetcher] = [MohwNewsFetcher(clock=clock)]
    for feed_url in settings.news_rss_feeds.split(","):
        if feed_url.strip():
            news_fetchers.append(RssNewsFetcher(feed_url=feed_url.strip(), clock=clock))
    if settings.news_api_key:
        news_fetchers.append(
            NewsApiFetcher(
                api_key=settings.news_api_key,
                clock=clock,
                query=settings.news_api_query,
                domains=settings.news_api_domains,
            )
        )
    jobs.append(
        build_news_crawl_job(
            fetchers=news_fetchers,
            store=news,
            hour=settings.longterm_consolidation_hour,
            minute=15,
        )
    )

    def _purge_expired_news() -> None:
        # 新聞與提及紀錄同一把保留天數：新聞被清掉後，提及紀錄留著也指不到東西。
        cutoff = clock().timestamp() - settings.news_retention_days * 86400
        news.purge_older_than(cutoff)
        core.news_mentions.purge_older_than(cutoff)

    jobs.append(
        build_news_cleanup_job(
            purge=_purge_expired_news,
            hour=settings.longterm_consolidation_hour,
            minute=50,
        )
    )
    # 標記長跑 job（見 `Job.background`）：這三支都要遍歷**全部長輩**並逐位呼叫 LLM，
    # 同步跑會把整輪掃描連同後面的 job 一起卡住。清理類的 job 不列入——它們是幾句
    # SQL，跑得比一次掃描還快，丟到背景只是多開執行緒。
    return [replace(job, background=job.name in _LONG_RUNNING_JOBS) for job in jobs]


def build_scheduler(
    settings: Settings, *, clock: Callable[[], datetime]
) -> tuple[Scheduler, Database]:
    externals = build_externals(settings)
    core = assemble_core(settings, externals, clock=clock)
    jobs = build_jobs(settings, core, clock=clock)
    state = PgScheduleStateStore(core.db, ZoneInfo(settings.timezone))
    return Scheduler(jobs, clock, state), core.db


def _watchdog(last_tick: list[float], *, stall_seconds: float, exit_now=os._exit) -> None:
    """卡住就自殺，交給 systemd 的 Restart=always 撿起來。

    ⚠️ 為什麼需要這一層（2026-07-26 全流程模擬實測）：實測抓到排程器「活著但停止
    運作」——程序在、CPU 幾乎零、日誌零成長，而每分鐘該跑的派送停了七小時、夜間
    批次停了十三天，`kinsun.sh status` 全程顯示 RUNNING。

    當時推斷是連線對端消失而本地無限期等待（已於 `db.py` 加 TCP keepalive），但
    現場證據其實**不支持**那個結論：`ss` 顯示 `Recv-Q=11988`，那是「資料已經到了、
    沒有人去讀」，不是「對端不見了」。也就是說**真正的根因沒有被證實**。
    所以這裡不賭任何一種診斷：不論它卡在 DB、卡在 mem0、還是卡在別的地方，
    只要 tick 停止推進就重啟。`Restart=always` 救得了程序掛掉，救不了假死——這條救得了。
    """
    while True:
        stalled = time.monotonic() - last_tick[0]
        if stalled > stall_seconds:
            logger.critical(
                "排程器停止推進 %.0f 秒（門檻 %.0f 秒），自我重啟交給 systemd 接手",
                stalled,
                stall_seconds,
            )
            exit_now(1)
        time.sleep(min(30.0, stall_seconds / 4))


_heartbeat_warned: list[bool] = [False]


def write_heartbeat(path: Path | None) -> None:
    """把「還在動」寫成檔案（epoch 秒），供 `kinsun.sh status` 判讀。

    ⚠️ 為什麼需要（2026-07-26 現場）：排程器假死七小時期間，`kinsun.sh status` 全程顯示
    RUNNING——因為它只看 PID 檔還在不在。**PID 活著不等於它在做事**，這個檔案補的正是
    這個差：狀態頁從此能分辨「行程活著」與「迴圈凍住」。

    設計借自 NousResearch/hermes-agent 的 `record_ticker_heartbeat`（`cron/jobs.py`）。
    刻意只取心跳這一個訊號，不照抄它的「上次成功」第二訊號：那是為了分辨「迴圈活著但
    每次 tick 都拋例外」，而我們的 `run_due` 逐 job 吞例外、不會拋，job 層級的真相已經
    記在 `scheduler_state.last_run_at`（後台 `/jobs` 的逾期告警讀的就是它）。

    盡力而為：寫不進去絕不可打斷 tick 迴圈；且只在第一次失敗時警告，
    否則每分鐘一行、一天 1440 行雜訊會把真正的錯誤淹掉。
    """
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.tmp")
        tmp.write_text(f"{time.time():.0f}\n", encoding="utf-8")
        tmp.replace(path)  # 原子換檔：status 永遠讀到完整的一行，不會讀到寫到一半的內容
    except Exception:  # noqa: BLE001 - 心跳只是觀測，不可拖垮排程
        if not _heartbeat_warned[0]:
            _heartbeat_warned[0] = True
            logger.warning("心跳檔寫入失敗，狀態頁將無法判讀假死 path=%s", path, exc_info=True)


def watchdog_stall_seconds(tick_seconds: int) -> float:
    """停止推進的門檻＝十個掃描間隔（預設 60s → 10 分鐘），下限 5 分鐘。

    夜間批次逐位長輩跑 LLM 可能跑很久，門檻太緊會在正常工作時誤殺；
    啟動階段（載 mem0／建連線池）實測不到 10 秒，同一個門檻綽綽有餘。
    """
    return max(300.0, tick_seconds * 10)


def start_watchdog(*, stall_seconds: float) -> list[float]:
    """啟動看門狗執行緒，回傳心跳；呼叫端每前進一步就 `heartbeat[0] = time.monotonic()`。

    ⚠️ 刻意讓 `main()` 在 `build_scheduler()` **之前**啟動，而不是包在 `serve()` 裡面。
    2026-07-26 23:00 的現場推翻了原本的假設：排程器當天重啟六次（16:05、16:11、17:11、
    17:14、19:09、19:31）全部卡在**啟動階段**——`main()` 那行「排程器啟動：…」橫幅一次
    都沒印出來，`schedule-dispatch` 停在 14:05 不動。看門狗若只守 tick 迴圈，這一整類的
    假死它一次也攔不到，因為迴圈根本還沒開始跑。
    """
    heartbeat = [time.monotonic()]
    threading.Thread(
        target=_watchdog,
        args=(heartbeat,),
        kwargs={"stall_seconds": stall_seconds},
        name="kinsun-scheduler-watchdog",
        daemon=True,
    ).start()
    return heartbeat


def serve(
    scheduler: Scheduler,
    *,
    tick_seconds: int,
    watchdog: bool = True,
    heartbeat: list[float] | None = None,
    heartbeat_path: Path | None = None,
) -> None:
    """tick 迴圈；`heartbeat` 由 `main()` 傳入（啟動階段就已在計時），沒傳才自己開一條。"""
    if heartbeat is None:
        heartbeat = (
            start_watchdog(stall_seconds=watchdog_stall_seconds(tick_seconds))
            if watchdog
            else [time.monotonic()]
        )
    while True:
        scheduler.run_due()
        heartbeat[0] = time.monotonic()
        write_heartbeat(heartbeat_path)
        time.sleep(tick_seconds)


def main() -> int:
    # ⚠️ 全庫原本沒有任何 logging 設定，root logger 停在預設的 WARNING、走
    # `logging.lastResort`（stderr、無時間戳、無 logger 名）——排程器新加的
    # `logger.info` 一行都不會出現，`exc_info` 印出來也查不出「何時開始壞的」。
    # 2026-07-26 全流程模擬實測才發現這件事。
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # `kill -USR1 <pid>`（或 `scripts/kinsun.sh dump scheduler`）→ 全執行緒 Python 堆疊
    # 直接倒進 stderr，也就是 logs/scheduler.log。
    # ⚠️ 為什麼非有不可：2026-07-26 排程器假死時，DGX 的 `ptrace_scope=1` 讓 py-spy 需要
    # root 才能附掛，而現場拿不到 root——結果是「明知它卡住，卻永遠不知道卡在哪一行」。
    # faulthandler 由行程自己印，不需要任何特權，下次假死就有堆疊可看。
    if hasattr(signal, "SIGUSR1"):  # Windows 沒有 SIGUSR1；開發機不該因此起不來
        try:
            faulthandler.register(signal.SIGUSR1, all_threads=True, chain=False)
        except (ValueError, OSError):
            # stderr 不是真的檔案描述子時（pytest 攔截輸出、某些嵌入式執行環境）註冊會失敗。
            # 這只是少了一個診斷工具，絕不能讓排程器因此起不來。
            logger.warning("SIGUSR1 堆疊傾印註冊失敗，假死時將無法取得 Python 堆疊")
    load_dotenv()
    settings = load_settings(os.environ)
    tz = ZoneInfo(settings.timezone)
    # 看門狗在 build_scheduler **之前**就開始計時：實測的六次假死全部發生在啟動階段
    # （見 start_watchdog）。晚一步啟動，就等於對這一整類故障失明。
    heartbeat = start_watchdog(
        stall_seconds=watchdog_stall_seconds(settings.scheduler_tick_seconds)
    )
    heartbeat_path = (
        Path(settings.scheduler_heartbeat_path) if settings.scheduler_heartbeat_path else None
    )
    # 啟動當下先寫一次：卡在啟動階段時，狀態頁看到的是「心跳越來越舊」而不是「沒有心跳」，
    # 前者是明確的假死訊號，後者會被誤讀成「還沒跑過」。
    write_heartbeat(heartbeat_path)
    scheduler, db = build_scheduler(settings, clock=lambda: datetime.now(tz))
    heartbeat[0] = time.monotonic()  # 啟動完成，交棒給 tick 迴圈
    # 問候那段不能再寫死「X:00」：自適應開啟時每位長輩各有各的時間，這行印的是機制。
    greeting = (
        f"問候 每半小時掃描（每位長輩各自的時間，"
        f"{settings.proactive_greeting_earliest_hour}-"
        f"{settings.proactive_greeting_latest_hour} 點，"
        f"未累積足夠資料前為 {settings.proactive_greeting_hour}:00）"
        if settings.proactive_greeting_adaptive_enabled
        else f"問候 {settings.proactive_greeting_hour}:00（自適應已關閉）"
    )
    print(
        f"排程器啟動：每 {settings.scheduler_tick_seconds}s 檢查；"
        f"整理 {settings.longterm_consolidation_hour}:05、"
        f"{greeting}、"
        f"失聯關心 {settings.proactive_inactivity_hour}:00"
        f"（{settings.proactive_inactivity_days} 天門檻）；"
        # 提醒不再是固定鐘點（D-76 P2）：每位長輩、每筆排程各有各的時刻，
        # 這行印的是機制而非時間表。
        f"排程提醒 每分鐘掃描（判定窗 {settings.schedule_dispatch_window_seconds}s）、"
        "舊表對帳 每 5 分鐘。"
    )
    try:
        serve(
            scheduler,
            tick_seconds=settings.scheduler_tick_seconds,
            heartbeat=heartbeat,
            heartbeat_path=heartbeat_path,
        )
    finally:
        db.close()
    return 0
