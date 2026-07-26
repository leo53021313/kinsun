"""主動關懷的排程 job。"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import datetime

from kinsun.proactive.preferences import GreetingPreferenceStore
from kinsun.scheduler.fanout import fanout_job
from kinsun.scheduler.scheduler import Job

logger = logging.getLogger("kinsun.proactive")

GREETING_INTENT = "早安問候，關心長者今天的狀況"
INACTIVITY_INTENT = "長者已經一段時間沒有互動了，主動表達想念與關心"


def greeting_intent(now: datetime, *, interests: Sequence[str] = ()) -> str:
    """早安問候的 intent 織入日期素材（2026-07-17 全功能測試）。

    固定 intent 天天餵，開場白也天天同一句——實測 4 次有 3 次逐字相同
    （「阿公早安，今天精神有沒有比較好？早餐吃了嗎？」）。日期與星期是
    每天必然不同的素材，給了模型才換得動話題；問候路徑已可走工具迴圈
    （agent.proactive），情境有定位座標時可順道報當地天氣。

    話題新聞改為工具引導（D-74 消費端，2026-07-25）：原本直接織入 2 則標題
    （push），改成提示模型自己用 get_news 查（pull）——模型從近 3 天的池子
    自行挑選、可依她的興趣帶 topic，且工具端已做「同一位長輩不重複給料」，
    開場話題才真的天天不同。

    interests（Leo 2026-07-25 興趣驅動挑題）：worker 於問候前從長期記憶檢索出的
    興趣線索（最多織入 3 條、各截 30 字），明示模型拿它當 get_news 的 topic——
    只靠「若記得她的興趣」的籠統提示，實測模型多半不會主動翻記憶找興趣。
    """
    weekday = "一二三四五六日"[now.weekday()]
    interest_hint = ""
    if interests:
        listed = "、".join(f"「{text[:30]}」" for text in list(interests)[:3])
        interest_hint = (
            f"記憶中她的興趣可能包含：{listed}——用 get_news 挑話題時，"
            "可優先拿相關關鍵字當 topic 試試。"
        )
    return (
        f"{GREETING_INTENT}。今天是 {now.month} 月 {now.day} 日、星期{weekday}，"
        "開場可以自然帶到今天的日子或這天的安排，不要每天都用同一句問候；"
        "情境若附上她目前的位置座標，可以先用天氣工具查當地天氣，順口提醒一句。"
        "想聊時事可以用 get_news 工具查最近的新聞，挑一則自然帶入就好、不必每次都提；"
        "若記得她的興趣，優先用 topic 參數挑她會有共鳴的主題。"
        f"{interest_hint}"
    )


# 每半小時掃描一次；偏好時間對齊半點（見 proactive/constants.py 的 SLOT_MINUTES），
# 兩者必須一致。
GREETING_SCAN_CRON = "0,30 * * * *"

# 補問候的時限（分鐘）。四小時是推導來的：既有契約要求「時段錯過仍要補」
# （test_it_still_greets_late_when_her_slot_was_missed：8:00 的長輩在 10:30 仍要收到），
# 所以下界至少要涵蓋 2.5 小時；上界則要擋掉實測踩到的情形——排程停擺一整天後
# 在晚上重啟，對全體長輩補送「早安」。四小時讓「早上恢復服務」照樣補得到，
# 「下午之後才恢復」則安靜跳過。
_GREETING_MAX_DELAY_MINUTES = 240

# 主動推播的可送時段（含頭不含尾）。長輩的作息不是我們的部署時間表——
# 排程器什麼時候被重啟是我們的事，不該變成她手機在半夜響。
_QUIET_START_HOUR = 7
_QUIET_END_HOUR = 21


def build_greeting_job(
    *,
    sessions: Callable[[], list[str]],
    greet_one: Callable[[str], object],
    default_hour: int,
    prefs: GreetingPreferenceStore | None,
    greeted_today: Callable[[str], bool],
    clock: Callable[[], datetime],
    name: str = "daily-greeting",
    max_delay_minutes: int = _GREETING_MAX_DELAY_MINUTES,
) -> Job:
    """每半小時掃描：已過她的偏好時間、且今天還沒問候過她，才問候（spec 2026-07-16）。

    為什麼是「已過且今天沒問候過」而非「精確比對時段」：worker 半夜當機重啟後，
    Scheduler 的補跨語意只會補跑一次，精確比對會讓該時段的長輩整天被漏掉。
    冪等由 greeted_today（讀 reminder_logs）保證。

    但「已過」不能沒有上界（2026-07-26 全流程模擬實測）：排程器停擺整天後，
    晚上九點半重新啟動，這條規則會對**當天所有沒被問候過的長輩**送出一句「早安」。
    實測當下正式環境有 64 位長輩、排程停擺十三天——重啟等於半夜集體吵醒。
    故補問候有時限：晚超過 `max_delay_minutes` 就當今天沒問候（明天照常），
    不是把早安留到深夜。

    prefs=None ＝ 一列偏好都不讀，全體回退 default_hour；這是
    PROACTIVE_GREETING_ADAPTIVE_ENABLED 這個緊急關閉開關的下游語意。只擋住夜間
    計算是不夠的——表裡還躺著上次算出來的時間，問候 job 若照樣讀，關掉開關等於
    什麼都沒關。
    """

    def action(elder_id: str) -> None:
        now = clock()
        pref = None
        if prefs is not None:
            try:
                pref = prefs.get_for_elder(elder_id)
            except Exception:  # noqa: BLE001 - 讀不到偏好就退回全域時間，不是停止問候
                # 降級成本功能之前的行為（全體同一時間），而非靜默停擺：偏好表持續
                # 失敗（權限、壞遷移）時仍有人被問候。代價是偏好晚於全域的長輩會被
                # 早問候一次——比整批長輩沒人理她好。
                logger.warning("問候偏好讀取失敗，改用全域時間 elder=%s", elder_id)
        target = pref.hour * 60 + pref.minute if pref else default_hour * 60
        minutes_now = now.hour * 60 + now.minute
        if minutes_now < target:
            return  # 還沒到她的時間
        if minutes_now - target > max_delay_minutes:
            # 晚太多就別問了：一句遲到十小時的「早安」比沒有更糟。
            logger.info("已超過補問候時限，今天不問候 elder=%s", elder_id)
            return
        # 刻意不接例外：讓它冒到 fanout 的 per-item try/except ＝ 跳過這位長輩。
        # 查不到「今天問候過沒」時寧可漏一次問候，也不可能重複轟炸長輩。
        if greeted_today(elder_id):
            return
        greet_one(elder_id)

    return fanout_job(
        name=name,
        cron=GREETING_SCAN_CRON,
        population=sessions,
        action=action,
        logger=logger,
    )


def build_inactivity_job(
    *,
    sessions: Callable[[], list[str]],
    last_active: Callable[[str], float | None],
    clock: Callable[[], datetime],
    threshold_seconds: float,
    care_one: Callable[[str], object],
    hour: int,
    minute: int = 0,
    name: str = "inactivity-care",
) -> Job:
    """久未互動的關懷推播；只在可推播時段送出。

    ⚠️ 理由與 `build_greeting_job` 的補跑時限同源（2026-07-26 全流程模擬實測）：
    排程器停擺後重啟，Scheduler 的補跨語意會讓這支排在早上十點的 job 立刻執行，
    夜裡重啟就在夜裡推播。這支沒有「每位長輩各自的時間」可比，故用固定的可送時段。
    """

    def action(elder_id: str) -> None:  # 會話主鍵已通道中立（✅ 庚-41 正名）
        now = clock()
        # ⚠️ 安靜時段（2026-07-26 全流程模擬實測）：排程器停擺後重啟時，補跨語意會讓
        # 這支排在早上十點的 job 立刻執行——晚上九點半重啟就在晚上推播，凌晨一點半
        # 重啟就在凌晨推播。關懷訊息晚幾小時沒關係，半夜送出去就是打擾。
        #
        # 用「時段」而不是「延遲多久」是刻意的：延遲要拿時分做減法，跨午夜會變成負數
        # 而恆通過（1:30 減 10:00 等於 -570），恰恰漏掉最該擋的那一格；時段判斷沒有這個坑，
        # 也不會讓後台的「立即執行」在上班時間變成無聲空轉。
        if not _QUIET_START_HOUR <= now.hour < _QUIET_END_HOUR:
            logger.warning("目前不在可推播時段，跳過失聯關心 elder=%s 時=%s", elder_id, now.hour)
            return
        last = last_active(elder_id)
        if last is not None and now.timestamp() - last >= threshold_seconds:
            care_one(elder_id)

    return fanout_job(
        name=name, hour=hour, minute=minute, population=sessions, action=action, logger=logger
    )
