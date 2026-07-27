"""觀測後台操作面（spec 2026-07-12 §3.4，內測限定）：排程手動執行＋提醒立即發送。

與 admin.py（唯讀觀測）分檔：本檔的 POST 端點都會改變系統狀態，
需 X-Admin-Key＋INTERNAL_TESTING_ENABLED 雙重守門。
手動觸發直接呼叫與 scheduler worker 同一份 job 函式、不寫 scheduler_state，
不干擾 worker 的到期判斷。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Literal

from croniter import croniter
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from kinsun import tracing
from kinsun.accounts.service import AccountService
from kinsun.channels.router import ChannelRouter
from kinsun.cron.registry import JobSpec
from kinsun.cron.scheduler import Job
from kinsun.cron.state import ScheduleStateStore
from kinsun.schedules.jobs import build_schedule_dispatch_job
from kinsun.schedules.models import RepeatKind, Schedule, ScheduleKind
from kinsun.schedules.store import ScheduleStore
from kinsun.web.envelope import ok
from kinsun.web.errors import ErrorCode
from kinsun.web.routers.admin import build_require_admin

# 逾期容許量：cron 與掃描都是分鐘級，沒有餘裕的話每支 job 在到期後的幾十秒內
# 都會被誤報。五分鐘足以吸收抖動，又遠小於實測到的停擺規模（七小時／十三天）。
_OVERDUE_TOLERANCE_SECONDS = 300.0


def _with_owners(names: list[str], owner_of: dict[str, str]) -> str:
    """把 job 名連同「誰該負責」一起寫進告警：`rag-weekly-refresh（rag_worker）`。

    owner 的字面刻意等於 `scripts/kinsun.sh` 的服務名，看到告警就能直接
    `kinsun.sh restart <owner>`——值班的人不必先去翻程式碼才知道要重啟誰。
    """
    return "、".join(f"{name}（{owner_of.get(name, '?')}）" for name in names)


class DispatchReminderBody(BaseModel):
    kind: Literal["medication", "appointment", "custom"]


class _ForcedDueStore:
    """讓派送 job 把某位長輩某一類的排程「當成現在到期」，供後台手動觸發。

    ⚠ mark_fired／mark_settled 刻意 **no-op**：手動觸發是內測工具，若讓它寫進真正的
    狀態欄，長輩當天真正該收到的那一則就不會發了——測試動作不可以吃掉正式提醒。
    """

    def __init__(self, inner: ScheduleStore, *, elder_id: str, kind: ScheduleKind) -> None:
        self._rows = [s for s in inner.list_for_elder(elder_id) if s.kind == kind]

    def list_due_once(self, *, until: float) -> list[Schedule]:
        return [s for s in self._rows if s.repeat_kind == RepeatKind.ONCE]

    def list_due_repeating(self, **kwargs) -> list[Schedule]:
        return [s for s in self._rows if s.repeat_kind != RepeatKind.ONCE]

    def mark_fired(self, schedule_id: str, *, now: float) -> None:
        return None

    def mark_settled(self, schedule_id: str, *, now: float) -> None:
        return None


# 手動觸發的 Opik root trace（工程觀測，OPIK_ENABLED 才生效）。FastAPI handler 因
# 依賴注入需保留原 signature，不能直接貼 @track，故把實際執行抽到這兩個 helper：
# worker 排程走 fanout 各自成 root，後台觸發則統一掛在此 root 下、標記為 admin 通道。
@tracing.track(name="admin_run_job", type="general", capture_input=True, ignore_arguments=["job"])
def _run_job_traced(job: Job) -> None:
    tracing.tag_current_trace(channel="admin", job=job.name)
    job.run()


@tracing.track(
    name="admin_dispatch_reminder",
    type="general",
    capture_input=True,
    ignore_arguments=["job"],  # Job 帶 callable，序列化沒有意義
)
def _dispatch_reminder_traced(job: Job, *, elder_id: str, kind: str) -> None:
    tracing.tag_current_trace(elder_id=elder_id, channel="admin", kind=kind)
    job.run()


def create_admin_jobs_router(
    *,
    admin_api_key: str,
    internal_testing_enabled: bool,
    specs: list[JobSpec],
    jobs: list[Job],
    schedule_state: ScheduleStateStore,
    accounts: AccountService,
    schedule_store: ScheduleStore,
    channel_router: ChannelRouter,
    record_reminder: Callable[[str, str, str], None],
    clock: Callable[[], datetime],
) -> APIRouter:
    router = APIRouter(tags=["admin"])
    require_admin = build_require_admin(admin_api_key)

    def require_testing() -> None:
        if not internal_testing_enabled:
            raise HTTPException(status_code=403, detail=ErrorCode.INTERNAL_TESTING_DISABLED)

    @router.get("/jobs", dependencies=[Depends(require_admin)])
    def list_jobs() -> dict:
        """各 job 的上次執行時間，**並標出逾期未跑的**。

        ⚠️ 為什麼需要 overdue（2026-07-26 全流程模擬實測）：排程器可能「活著但停止
        運作」——程序在、`kinsun.sh status` 顯示 RUNNING、日誌零成長，而每分鐘該跑的
        派送停了七個小時、夜間批次停了十三天，沒有任何地方會叫。這一頁本來就有
        `last_run_at`，缺的只是「有沒有人拿它跟 cron 比一下」。

        判定看的是 job 本身有沒有按時跑，不是程序在不在——程序被停掉、卡死、當掉，
        三種情形都會在這裡浮現。

        ⚠️ 母體是 `cron/registry.py` 的**全系統**宣告，不是本程序綁得出來的那些
        （2026-07-27）。原本逐一走 `jobs`（＝主排程器那一份），於是 `rag-weekly-refresh`
        對這一頁完全不存在：RAG 週更程序掛掉、`RAG_REFRESH_ENABLED` 忘了開、從部署起
        一次都沒跑過，這一頁一律全綠。一個只看得到自己程序的健康檢查，抓不到的正是
        它最該抓的那種故障。
        """
        now = clock()
        runnable = {job.name for job in jobs}
        items = []
        overdue: list[str] = []
        never_ran: list[str] = []
        failing: list[str] = []
        for spec in specs:
            last = schedule_state.get_last_run(spec.name)
            due_at = croniter(spec.cron, last).get_next(datetime) if last else None
            # 容許量＝一個掃描間隔再加點餘裕：cron 是分鐘級、掃描也是分鐘級，
            # 沒有容許量的話每個 job 在到期後的那幾十秒都會被誤報成逾期。
            late_seconds = (now - due_at).total_seconds() if due_at else 0.0
            # 容許量逐 job 決定：`schedule-dispatch` 的判定窗只有 90 秒且窗外不補，
            # 沿用 300 秒的預設會在提醒**已經永久遺失**時仍顯示健康（2026-07-27 修）。
            tolerance = (
                spec.max_lateness_seconds
                if spec.max_lateness_seconds is not None
                else _OVERDUE_TOLERANCE_SECONDS
            )
            is_overdue = late_seconds > tolerance
            # ⚠️ 從沒跑過（`scheduler_state` 沒有這一列）必須單獨標出來，不可算成健康：
            # 沒有 last_run_at 就算不出 due_at，`is_overdue` 於是恆為 False——一支
            # 從部署起就沒被排程器碰過的 job，這一頁會顯示成全綠。那正是這一頁要抓的
            # 情形裡最嚴重的一種（例如排程器根本沒認得這支 job、或它從未啟動過）。
            is_never_ran = last is None
            # ⚠️ 「一直在跑、但一直失敗」是這一頁先前完全看不見的盲區（2026-07-27）：
            # `last_run_at` 由 `_claim_if_due` 在執行**之前**寫入（at-most-once 搶占所
            # 必需），所以每輪都拋例外的 job 照樣按時更新 last_run_at，上面的 is_overdue
            # 永遠是 False——後台顯示全綠。要靠獨立的成功訊號才分得出來。
            #
            # `last_success_at` 為 None 有兩種可能：真的從沒成功過，或這一列是本欄上線前
            # 的舊資料。兩者都**不可**當成失敗——否則第一次部署整排變紅、狼來了一次之後
            # 就沒人再看這一頁了。故只在「有成功紀錄、但落後超過一個容許量」時才報。
            last_success = schedule_state.get_last_success(spec.name)
            is_failing = (
                last_success is not None
                and last is not None
                and (last - last_success).total_seconds() > tolerance
            )
            if is_never_ran:
                never_ran.append(spec.name)
            elif is_overdue:
                overdue.append(spec.name)
            elif is_failing:
                failing.append(spec.name)
            items.append(
                {
                    "job_name": spec.name,
                    "cron": spec.cron,
                    # 哪個程序負責跑它。逾期時要去重啟的不一定是排程器——沒有這一欄，
                    # 值班的人會對著健康的排程器查半天，而該修的是另一個程序。
                    "owner": spec.owner,
                    # 本程序綁不出執行體的 job（例如 RAG 週更）沒有「立即執行」可用，
                    # 前端據此停用按鈕，而不是讓人按下去才吃 409。
                    "can_run_now": spec.name in runnable,
                    "last_run_at": last.timestamp() if last else None,
                    "due_at": due_at.timestamp() if due_at else None,
                    "late_seconds": round(late_seconds) if is_overdue else 0,
                    "is_overdue": is_overdue,
                    "never_ran": is_never_ran,
                    # None＝還沒有成功紀錄（含本欄上線前的舊列）；前端顯示「未知」不是紅字。
                    "last_success_at": last_success.timestamp() if last_success else None,
                    "is_failing": is_failing,
                }
            )
        owner_of = {spec.name: spec.owner for spec in specs}
        warnings = []
        if overdue:
            warnings.append(
                f"有 {len(overdue)} 支排程逾期未執行：{_with_owners(overdue, owner_of)}"
                "（該程序可能沒在跑或已卡死，程序活著也可能停擺）"
            )
        if never_ran:
            warnings.append(
                f"有 {len(never_ran)} 支排程從未執行過：{_with_owners(never_ran, owner_of)}"
                "（首次部署後會先種基準，若持續顯示請確認該程序有啟動、且有認到這支 job）"
            )
        if failing:
            warnings.append(
                f"有 {len(failing)} 支排程按時執行但持續失敗：{_with_owners(failing, owner_of)}"
                "（有被認領、但最後一次成功已落後；請查該 job 的 log，"
                "外部配額或憑證失效是常見原因）"
            )
        return ok(
            items,
            meta={
                "overdue": overdue,
                "never_ran": never_ran,
                "failing": failing,
                "warnings": warnings,
            },
        )

    @router.post(
        "/jobs/{job_name}/run",
        dependencies=[Depends(require_admin), Depends(require_testing)],
    )
    def run_job(job_name: str) -> dict:
        job = next((j for j in jobs if j.name == job_name), None)
        if job is None:
            # 「這一頁看得到但按不動」與「根本沒這支 job」是兩件事，錯誤碼必須分開：
            # 前者是設計如此（RAG 週更跑數小時、只需 DB 與 Gemini，刻意住在別的程序，
            # 不該由一條 HTTP 請求拖著跑），後者是打錯名字。混成同一個 404，值班的人
            # 會以為後台壞了。
            spec = next((s for s in specs if s.name == job_name), None)
            if spec is not None:
                raise HTTPException(status_code=409, detail=ErrorCode.JOB_NOT_RUNNABLE_HERE)
            raise HTTPException(status_code=404, detail=ErrorCode.JOB_NOT_FOUND)
        _run_job_traced(job)  # 同步執行；內測工具，接受長任務佔用一個 worker thread
        return ok({"job_name": job.name, "ran_at": clock().timestamp()})

    @router.post(
        "/elders/{elder_id}/reminders/dispatch",
        dependencies=[Depends(require_admin), Depends(require_testing)],
    )
    def dispatch_reminder(elder_id: str, body: DispatchReminderBody) -> dict:
        if accounts.get_elder(elder_id) is None:
            raise HTTPException(status_code=404, detail=ErrorCode.ELDER_NOT_FOUND)
        kind = ScheduleKind(body.kind)
        forced = _ForcedDueStore(schedule_store, elder_id=elder_id, kind=kind)
        job = build_schedule_dispatch_job(
            store=forced,
            lookup_elder=accounts.get_elder,
            guardians_of=accounts.guardians_of,
            router=channel_router,
            clock=clock,
            record=record_reminder,
            name=f"manual-{body.kind}",
        )
        _dispatch_reminder_traced(job, elder_id=elder_id, kind=body.kind)
        count = len(forced.list_due_once(until=0)) + len(forced.list_due_repeating())
        return ok({"kind": body.kind, "count": count})

    return router
