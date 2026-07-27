"""排程工具：長輩用說的建立、查詢與取消提醒（D-76 P4）。

**全庫第一組會寫資料庫的工具。** 四條安全界線因此寫死在這裡：

1. `elder_id` 一律從 `ToolInvocationContext` 取，**不接受模型傳入**。模型若能指定
   對象，就等於能改別人的排程——這是提示詞注入最直接的獲利路徑。
2. 長輩不能取消家屬設的排程（規則在 Service，這裡只負責把白話理由講出來）。吃藥
   與回診是家人替他把關的事，一句「不要再提醒我吃藥了」就刪掉等於幫他停藥。
3. 筆數上限由 Service 把關，工具只轉述——防的是模型連續誤判把行程表灌爆。
4. 長輩這一輪沒開口就不得寫入（`_requires_utterance`）。主動關懷（`CareAgent.proactive`）
   也走同一個工具迴圈、拿得到同一組工具，但那一輪長輩根本沒說話——實測（2026-07-27）
   一次早安問候就把一筆長輩從未答應的提醒寫進了資料庫，而且到時間真的會響。

工具回傳的字串是**給模型看的素材**，不是直接送給長輩的話。措辭仍寫成白話，因為
模型最可靠的行為是照抄；驗證錯誤更是原樣轉述（Service 的訊息本來就是白話）。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from kinsun.llm import ToolSpec
from kinsun.schedules.models import CreatedBy, Occurrence, RepeatKind, ScheduleGroup, ScheduleKind
from kinsun.schedules.service import ScheduleService, ScheduleValidationError
from kinsun.schedules.timeparse import TimeParseError, build_occurrence
from kinsun.tools.registry import ToolInvocationContext
from kinsun.turn_context import current_utterance, record_action

logger = logging.getLogger("kinsun.tools.schedules")

_WEEKDAYS = "一二三四五六日"
_NO_ELDER = "（目前不知道是誰在講話，沒辦法幫他記事情）"
_NO_UTTERANCE = "（長輩這一輪沒有開口，不可以替他動提醒。等他自己講再說。）"


def _requires_utterance() -> bool:
    """這一輪長輩真的開口了嗎？（安全界線 4）

    ⚠️ 這道防線的形狀刻意與 `weather._is_from_elder` 一致，但防的是不同的事：天氣防的是
    「地名是模型猜的」，這裡防的是「整輪對話根本沒有長輩」。主動關懷把原話明確設為空
    字串（`agent.proactive` 的 `elder_utterance("")`），故空字串＝長輩沒開口。

    只擋寫入（create／cancel），不擋 `list_schedules`——問候要看得到今天有什麼事才講得
    出話，而唯讀不會留下長輩沒同意的後果。

    為什麼防線在工具內而不是在 registry 加「本輪允許哪些工具」的名單：名單要嘛列
    唯讀工具（日後新增工具漏列＝問候悄悄少一個能力），要嘛列寫入工具（漏列＝重演本次
    漏洞）。放在工具內則是「會寫庫的工具自己負責確認有人授權」，新工具的作者複製這個
    檔當範本時會直接看到這條界線。
    """
    return bool(current_utterance())


CREATE_SPEC = ToolSpec(
    name="create_schedule",
    description=(
        "幫長輩記下一件要提醒的事。長輩講出具體時間又答應要提醒時才呼叫；"
        "他只是隨口聊到、沒有明確時間，就不要用這個工具。"
        "吃藥用 medication、回診用 appointment、其他生活的事用 custom。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "要提醒的事，例如「去吃飯」「血壓藥」"},
            "kind": {
                "type": "string",
                "enum": ["medication", "appointment", "custom"],
                "description": "提醒類型",
            },
            "repeat": {
                "type": "string",
                "enum": ["once", "daily", "weekly"],
                # ⚠️ 判準寫死（2026-07-26 全流程模擬實測）：長輩說「禮拜五下午兩點孫子
                # 要來」被記成 weekly，於是每個禮拜五都提醒他孫子要來——一次性的家庭
                # 聚會變成每週騷擾，而且長輩多半不會主動說「幫我取消」。
                # 只寫「weekly＝每週」不夠：講出星期幾在中文裡本來就常指「這個禮拜五」。
                "description": (
                    "once＝只提醒一次；daily＝每天；weekly＝每週。"
                    "長輩只講星期幾（例如「禮拜五孫子要來」），沒有明說「每週」「每個禮拜」"
                    "「以後都」的時候，一律用 once，不可以自己升級成 weekly。"
                ),
            },
            "date": {
                "type": "string",
                "description": (
                    "once 用，格式 2026-07-30。長輩只講星期幾沒講日期時，"
                    "自己換算成最近的那一天（今天就是那天且時刻還沒過，就用今天）。"
                ),
            },
            "time": {"type": "string", "description": "事件發生的時刻，格式 20:45"},
            "weekday": {
                "type": "integer",
                "description": "weekly 用，0 是星期一、6 是星期日",
            },
            "in_minutes": {
                "type": "integer",
                "description": "長輩說「幾分鐘後」「一小時後」時填，會蓋過 date／time",
            },
            "advance_minutes": {
                "type": "integer",
                "description": "要提早幾分鐘提醒（你提議、長輩同意的那個數字）；準時就填 0",
            },
        },
        "required": ["title", "kind", "repeat"],
    },
)

LIST_SPEC = ToolSpec(
    name="list_schedules",
    description="查長輩目前有哪些提醒。他問「我今天有什麼事」或你要幫他取消某件事之前使用。",
    parameters={"type": "object", "properties": {}},
)

CANCEL_SPEC = ToolSpec(
    name="cancel_schedule",
    description=(
        "取消一件提醒。先用 list_schedules 查到編號，再把該筆的 group_id 帶進來。"
        "家人幫他設定的提醒不能由他取消，工具會告訴你。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "group_id": {"type": "string", "description": "list_schedules 回傳的那個編號"}
        },
        "required": ["group_id"],
    },
)


def _describe(group: ScheduleGroup, now: datetime) -> str:
    first = group.schedules[0]
    if first.repeat_kind == RepeatKind.DAILY:
        when = f"每天 {first.repeat_time}"
    elif first.repeat_kind == RepeatKind.WEEKLY:
        weekday = _WEEKDAYS[first.repeat_weekday] if first.repeat_weekday is not None else ""
        when = f"每週{weekday} {first.repeat_time}"
    else:
        moment = group.event_at if group.event_at is not None else first.scheduled_at
        stamp = datetime.fromtimestamp(moment, now.tzinfo) if moment else now
        when = f"{stamp.month}月{stamp.day}日 {stamp.strftime('%H:%M')}"
    return f"{when} {group.title}"


def _as_int(value, field: str) -> int | None:
    """把模型送來的數字參數轉成 int；轉不動就拋白話的 TimeParseError。

    ⚠️ 為什麼需要（2026-07-27 實測）：模型送 `weekday="3"`（字串）時，`timeparse` 的
    `0 <= weekday <= 6` 會拋 `TypeError: '<=' not supported between instances of
    'int' and 'str'`——這句**英文原文**會被 handler 的 except 包進回傳字串、餵回模型的
    context，最壞的情況是金孫照著唸給長輩聽。JSON Schema 標了 integer 也擋不住，
    模型該送字串時照樣送。

    能轉就轉（字串數字是常見且無害的變體），轉不動才拒絕，且用白話拒絕。
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise TimeParseError(f"{field}要給數字。") from exc


def _occurrence_for(arguments: dict, *, now: datetime) -> tuple[Occurrence, float | None]:
    """回傳（鬧鐘, 事件時刻）。

    參數描述的是**事件**何時發生；提醒時刻 ＝ 事件時刻減去 advance_minutes（決策 9：
    提前量由金孫提議、長輩一句話認可）。提前量為 0 時事件時刻留 None，措辭才會走
    「提醒您」而不是「再過 n 分鐘」。
    """
    # 三個數字參數統一經 `_as_int` 轉型：模型送字串數字是常見行為，而未轉型會讓
    # Python 的英文例外原文流進模型 context（見 `_as_int` 的說明）。
    advance = max(0, _as_int(arguments.get("advance_minutes"), "提前幾分鐘") or 0)
    in_minutes = _as_int(arguments.get("in_minutes"), "幾分鐘後")
    if in_minutes is not None:
        event_at = (now + timedelta(minutes=in_minutes)).timestamp()
        return Occurrence(RepeatKind.ONCE, scheduled_at=event_at - advance * 60), (
            event_at if advance else None
        )
    occurrence = build_occurrence(
        repeat=str(arguments.get("repeat", "")),
        time_text=str(arguments.get("time", "")),
        date_text=str(arguments.get("date", "")),
        weekday=_as_int(arguments.get("weekday"), "星期幾"),
        now=now,
    )
    if occurrence.repeat_kind != RepeatKind.ONCE or not advance:
        # 重複型不支援提前量：講「每天提早十分鐘」等於直接把時刻往前挪，
        # 模型應該給挪好的時刻，而不是讓兩個欄位同時描述同一件事。
        return occurrence, None
    event_at = occurrence.scheduled_at
    return Occurrence(RepeatKind.ONCE, scheduled_at=event_at - advance * 60), event_at


def build_create_handler(
    schedules: ScheduleService, *, clock: Callable[[], datetime]
) -> Callable[[dict, ToolInvocationContext | None], str]:
    def handler(arguments: dict, context: ToolInvocationContext | None = None) -> str:
        # ⚠ 安全關鍵：對象只認 context，永不讀 arguments 裡的 elder_id。
        elder_id = context.elder_id if context else ""
        if not elder_id:
            return _NO_ELDER
        if not _requires_utterance():
            return _NO_UTTERANCE
        now = clock()
        try:
            occurrence, event_at = _occurrence_for(arguments, now=now)
        except (TimeParseError, TypeError, ValueError) as exc:
            return f"（沒辦法記下來：{exc}）"
        try:
            kind = ScheduleKind(str(arguments.get("kind", ScheduleKind.CUSTOM.value)))
        except ValueError:
            kind = ScheduleKind.CUSTOM
        try:
            rows = schedules.create(
                elder_id=elder_id,
                kind=kind,
                title=str(arguments.get("title", "")),
                created_by=CreatedBy.ELDER,
                occurrences=(occurrence,),
                event_at=event_at,
            )
        except ScheduleValidationError as exc:
            return f"（沒辦法記下來：{exc}）"
        group = ScheduleGroup(
            group_id=rows[0].group_id,
            elder_id=elder_id,
            kind=kind,
            title=rows[0].title,
            created_by=CreatedBy.ELDER,
            schedules=tuple(rows),
        )
        # 寫入成功才登記（見 turn_context.turn_actions）：出站防線據此分辨
        # 「金孫真的記下來了」與「金孫只是嘴上答應」。驗證失敗的路徑在上面就 return 了。
        record_action(CREATE_SPEC.name)
        return f"已經記下來了：{_describe(group, now)}。請照這個時間跟長輩複誦一次。"

    return handler


def build_list_handler(
    schedules: ScheduleService, *, clock: Callable[[], datetime]
) -> Callable[[dict, ToolInvocationContext | None], str]:
    def handler(arguments: dict, context: ToolInvocationContext | None = None) -> str:
        elder_id = context.elder_id if context else ""
        if not elder_id:
            return _NO_ELDER
        now = clock()
        groups = schedules.groups_for_elder(elder_id)
        if not groups:
            return "目前沒有任何提醒。"
        lines = [f"{_describe(g, now)}（編號 {g.group_id}）" for g in groups]
        return "目前的提醒：\n" + "\n".join(lines)

    return handler


def build_cancel_handler(
    schedules: ScheduleService,
) -> Callable[[dict, ToolInvocationContext | None], str]:
    def handler(arguments: dict, context: ToolInvocationContext | None = None) -> str:
        elder_id = context.elder_id if context else ""
        if not elder_id:
            return _NO_ELDER
        if not _requires_utterance():
            return _NO_UTTERANCE
        group_id = str(arguments.get("group_id", ""))
        # 只能取消自己名下的：不比對就等於誰都能拿別人的 group_id 來刪。
        if group_id not in {g.group_id for g in schedules.groups_for_elder(elder_id)}:
            return "（找不到這筆提醒，請先用 list_schedules 查一次）"
        try:
            schedules.cancel_group(group_id, requested_by=CreatedBy.ELDER)
        except ScheduleValidationError as exc:
            return f"（不能取消：{exc}）"
        return "已經取消了，請跟長輩說一聲。"

    return handler
