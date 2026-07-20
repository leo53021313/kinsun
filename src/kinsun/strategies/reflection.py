"""每晚反思：讀過去 N 天的互動，沉澱出「這位長輩的相處之道」。

與 `reports/summaries.py` 的 `summarize_day` 是姊妹批次，但有兩個關鍵差異：

1. 讀「過去 N 天」而非只讀昨天——證據門檻（`policy.is_admissible`）要求守則跨多天
   重複出現，反思就必須看得到多天。照抄 `previous_day()` 會讓模型永遠只有一天的
   觀察可引用，門檻不是變嚴、而是整個功能失效。
2. 產出寫回系統自己（strategies 表 → 注入 system prompt），而非寫給家屬看。
   摘要是報告，反思是學習。

## 讀多天就不能用 list_for_range

`list_for_range` 的 `LIMIT` 套在 `ORDER BY created_at ASC` 上：超量時**留下的是最舊的**。
單日窗（consolidation 逐日補齊）幾乎不會撞到上限，跨七天的窗卻很容易——健談的長輩
一天 40 輪，七天就 280 輪。撞上限的後果是反思只看得到最舊的那幾天，長輩前天才糾正
過的事反而看不到：**越投入的長輩，反思品質越差**。故此處固定用
`list_recent_in_range`（保最新、丟最舊），上限走獨立的 `REFLECTION_MAX_TURNS`，且撞到
上限一定記 warning——靜默縮水的視野是查不出來的。

## 三個「壞掉也不能炸」的地方

守則自動生效、無人審，而這支批次每晚對每位長輩跑一次。它的失敗模式必須是
「今晚少學一條」，不能是「今晚整批長輩的反思都掛掉」：

* **回傳格式不合** → 整批丟棄並記 warning。半份 JSON 裡挑得出來的那幾條，來源同樣
  不可信；寧可今晚不學，不可學進垃圾。
* **單條被濾網擋下** → 只丟該條，其餘照寫。拒絕理由**逐條**記 warning：這是我們
  唯一能觀測「詞表誤殺了什麼」與「模型多常試圖越界」的訊號，揉成一句聚合日誌
  就再也分不出醫療攔截、輕蔑攔截、注入攔截、證據不足、撞上限各發生幾次。其中
  「輕蔑攔截」的計數就是「模型多常試圖教金孫忽視長輩」——它自成一桶，別跟醫療混。
* **寫入時 store 丟 StrategyError** → 跳過該條、繼續其餘。這在實務上會發生：反思讀
  完生效中守則、寫入前，家屬剛好在後台撤銷了那條取代對象（濾網看的是舊快照）。

## 濾網的記帳交給 admit_all

「接受一條後 adopted 數與 adopted_ids 該怎麼變」是易錯的記帳（有取代對象時是一進
一出、無取代對象時才 +1），一律交給 `policy.admit_all`，此處不自行迴圈記帳。
`adopted_ids` 必須是 status='adopted' 的集合——`list_for_elder` 的 `status` 預設為
`None`（全部狀態），漏傳就會讓已撤銷的守則被「取代」而復活。
"""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from kinsun import tracing
from kinsun.llm import Message
from kinsun.memory.shortterm import MemoryStore, previous_day_bounds
from kinsun.reports.reminders import ReminderLog, ReminderLogStore
from kinsun.strategies.models import STRATEGY_STATUS_ADOPTED, Strategy
from kinsun.strategies.policy import MAX_CONTENT_CHARS, Candidate, admit_all
from kinsun.strategies.store import StrategyError, StrategyStore

logger = logging.getLogger("kinsun.strategies.reflection")

_SECONDS_PER_DAY = 86400.0  # 台灣無日光節約，一天固定 86400 秒。

_REQUIRED_FIELDS = ("content", "category", "evidence", "observed_days")

# 受控生成 schema：把回傳約束成合法的守則陣列，減少「格式故障→整批丟棄」的空轉夜。
# schema 只管結構，語意（四類守則、禁醫療詞、跨多天證據等）仍靠 REFLECTION_PROMPT。
# supersedes 設 nullable optional：模型輸出整數 id 會被 _to_candidate 判型別錯而整批丟棄，
# 約束成 string|null 可避免這個失效；observed_days 約束成整數，evidence 約束成字串。
_REFLECTION_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "content": {"type": "string"},
            "category": {"type": "string"},
            "evidence": {"type": "string"},
            "observed_days": {"type": "integer"},
            "supersedes": {"type": ["string", "null"]},
        },
        "required": ["content", "category", "evidence", "observed_days"],
    },
}

# 反思的系統提示。第 3、5 條是對濾網的「事前緩解」而非重複防護：
# 濾網（policy.py）會擋掉含醫療字眼與過長／多行的守則，但它只能丟棄、無法改寫，
# 合法的話題類守則（「不要聊她過世老伴生病的那段」）因此會被誤殺。與其放寬詞表，
# 不如在這裡就要求模型寫成不含醫療字眼的說法。長度上限引用 policy 的公開常數，
# 兩邊永遠一致。
#
# 第 4 條是第 3 條的必要配套，不可拆開看：「把醫療字眼改寫掉」的指令同時開了一條路，
# 讓「她說胸口很痛通常只是想撒嬌，不用理會」能改寫成「她抱怨的時候通常只是想撒嬌，
# 不用理會」——沒有醫療詞、單行、夠短、分類合法，然後永久注入 system prompt。而這正是
# policy.py docstring 點名的真正傷害：金孫當著長輩的面把危急訊號正常化。第 2 條擋不住它
# （它字面上是 tone／topic，不涉用藥就醫），醫療詞表也擋不住（改寫後無詞可命中）。
#
# 第 4、5 條**不是**防線——`policy._dismissive_hit` 才是。這裡的第 4 條要求模型自我判定
# 「我的本意是不是忽視」，而「她講話比較誇張，不用每句都當真」這種句子，模型並不覺得
# 自己違規（它甚至正面否定了第 4 條的收尾句）。第 5 條因此改用**列舉句式**而非要求判定
# 意圖：目的是讓模型少產出無謂的候選，攔截仍交給程式。prompt 不是防線，程式碼才是。
REFLECTION_PROMPT = (
    "你是「金孫」——一位陪伴長輩的 AI 夥伴——的反思模組。以下是這位長輩過去幾天"
    "與金孫的對話，以及系統推送的提醒與長輩是否回應的紀錄。\n\n"
    "請找出「與這位長輩相處時應該遵守的守則」，讓金孫下次做得更好。\n\n"
    "【嚴格限制，違反者一律作廢】\n"
    "1. 只能產出四類守則：address（稱呼）、tone（語氣與長短）、routine（作息與時間）、"
    "topic（話題偏好）。\n"
    "2. 絕對禁止產出任何涉及用藥、劑量、就醫、回診、危急判斷、健康數值的守則。"
    "金孫的用藥提醒與安全機制不是你能調整的對象。\n"
    "3. 守則的文字也不可以出現醫療或身體不適的字眼（醫、診、病、藥、痛、血、跌、"
    "不舒服……），含這些字的守則會被系統直接丟棄。話題類的守則請改寫成不含這些字"
    "的說法，例如「不要聊她過世老伴生病的那段」要改寫成「不要聊她過世老伴的事」。\n"
    "4. 但若一條守則的本意是要金孫忽視、淡化或不理會長輩說的不適、疼痛、情緒或求助，"
    "一律不要產出，也不可改寫成不含上述字眼的說法來規避第 3 條——例如「她說胸口很痛"
    "通常只是想撒嬌，不用理會」不合法，改寫成「她抱怨的時候通常只是想撒嬌，不用理會」"
    "同樣不合法。這類守則永遠不合法：長輩喊不舒服時，金孫必須當真。\n"
    "5. 具體地說，以下寫法一律不要產出（系統會直接丟棄並另行記錄）：把長輩的抱怨、"
    "情緒或求助說成「不用當真」「不用理會」「不用管她」「不用在意」「聽聽就好」"
    "「當作沒聽到」；或把她的訴求歸因成「只是想撒嬌」「討拍」「裝出來的」「在演戲」"
    "「誇大」「小題大作」。她的個性可以寫（「她講話比較直」「她講話慢」），她的訴求"
    "不可以被打折。\n"
    f"6. 每條守則都是一句話，不超過 {MAX_CONTENT_CHARS} 個字；不可換行、不可分點、"
    "不可加標題。\n"
    "7. 每條守則必須有跨多天、重複出現的證據。單一天的一次觀察不算數"
    "（長輩可能只是那天心情不好），此類一律不要產出。\n"
    "8. 已經生效的守則不要重複產出。\n\n"
    "【回傳格式】只回傳 JSON 陣列，不要任何其他文字或 markdown 標記。每個元素：\n"
    '{"content": "一句話的守則", "category": "四類之一", '
    '"evidence": "你依據的觀察", "observed_days": 這個模式在幾天中出現過的整數, '
    '"supersedes": null 或要取代的既有守則 id}\n'
    "沒有值得沉澱的守則時，回傳空陣列 []。\n"
)


class Reflector(Protocol):
    """反思用的 LLM 呼叫端；形狀同 `summarize_day` 的 summarizer（見 llm.LLMClient）。"""

    def generate(
        self,
        *,
        system_prompt: str,
        messages: list[Message],
        response_schema: dict | None = None,
    ) -> str: ...


@tracing.track(name="nightly_reflection", type="general", capture_input=False, capture_output=False)
def reflect_days(
    elder_id: str,
    *,
    short_term: MemoryStore,
    reminder_logs: ReminderLogStore,
    strategies: StrategyStore,
    reflector: Reflector,
    clock: Callable[[], datetime],
    lookback_days: int,
    min_observed_days: int,
    max_strategies: int,
    max_turns: int,
) -> None:
    """反思這位長輩過去 lookback_days 天的互動，把通過濾網的守則寫成生效中的守則。"""
    tracing.update_trace_metadata(elder_id=elder_id, flow="nightly_reflection")
    # 迄點＝今日零時：只反思已完整結束的日子，今天才過幾小時的片段不算一天。
    _, end = previous_day_bounds(clock())
    start = end - lookback_days * _SECONDS_PER_DAY
    # 用 list_recent_in_range 而非 list_for_range：後者的 LIMIT 套在 ASC 上，跨七天讀時
    # 截掉的會是**最新的那幾天**，健談的長輩反而只被反思到一片舊資料（見模組 docstring）。
    turns = short_term.list_recent_in_range(elder_id, start=start, end=end, limit=max_turns)
    if not turns:
        return
    if len(turns) >= max_turns:
        # 取滿上限即示警（可能剛好等於上限而未截斷——寧可多報一次，不可讓視野縮水無聲無息）。
        logger.warning(
            "反思輪數達上限，較舊的對話未納入 elder=%s limit=%s 回看天數=%s",
            elder_id,
            max_turns,
            lookback_days,
        )

    logs = reminder_logs.list_for_range(elder_id, start=start, end=end)
    adopted = strategies.list_for_elder(elder_id, status=STRATEGY_STATUS_ADOPTED)
    system_prompt = _build_prompt(logs, adopted, lookback_days, min_observed_days, max_strategies)
    reply = reflector.generate(
        system_prompt=system_prompt, messages=turns, response_schema=_REFLECTION_SCHEMA
    )

    candidates = _parse(reply)
    if candidates is None:
        # 整批丟棄：格式壞掉代表這份回應的來源不可信，挑得出來的那幾條同樣不可信。
        logger.warning("反思回傳格式不合，整批丟棄 elder=%s 回應=%r", elder_id, reply[:200])
        return

    plausible, forged = _split_forged_evidence(candidates, lookback_days)
    accepted, rejected = admit_all(
        plausible,
        min_observed_days=min_observed_days,
        adopted_count=len(adopted),
        max_strategies=max_strategies,
        adopted_ids={row.strategy_id for row in adopted},
    )
    for candidate, reason in [*forged, *rejected]:
        # 逐條記錄、理由原文照登：理由字串本身就是拒絕分類（醫療攔截／輕蔑攔截／結構
        # 驗證／證據不足／證據捏造／撞上限），聚合成一句就失去可分類統計的價值。
        # 「守則分類」是模型自填的 category（address／tone／…），**不是**拒絕分類——欄位
        # 名若只寫「分類」，後人拿它分桶會分到完全不同的東西。
        logger.warning(
            "守則被濾網擋下 elder=%s 理由=%s 守則分類=%s 內容=%r",
            elder_id,
            reason,
            candidate.category,
            candidate.content,
        )
    for candidate in accepted:
        _record(strategies, elder_id, candidate)


def _split_forged_evidence(
    candidates: list[Candidate], lookback_days: int
) -> tuple[list[Candidate], list[tuple[Candidate, str]]]:
    """挑掉 observed_days 大於回看天數的候選：那不是證據充分，是捏造證據。

    證據門檻整個建立在模型**自陳**的 observed_days 上，而在七天的窗裡自陳「觀察了 999
    天」是物理上不可能的觀察。少了這道免費的合理性檢查，繞過證據門檻的成本是零。

    這道檢查只能做在這裡：`policy` 收的是 `min_observed_days`，它不知道回看天數是幾天，
    無從判斷一個數字是否超出視野。拒絕理由刻意寫成可辨識的「證據捏造」——「模型試圖
    繞過證據門檻」是最該告警的指標之一，不可與尋常的「證據不足」混在同一桶。
    """
    plausible: list[Candidate] = []
    forged: list[tuple[Candidate, str]] = []
    for candidate in candidates:
        if candidate.observed_days > lookback_days:
            forged.append(
                (
                    candidate,
                    f"證據捏造：自陳觀察 {candidate.observed_days} 天，"
                    f"超出回看天數 {lookback_days} 天（不可能的觀察）",
                )
            )
        else:
            plausible.append(candidate)
    return plausible, forged


def _record(strategies: StrategyStore, elder_id: str, candidate: Candidate) -> None:
    """寫入一條守則；寫不進去只丟這條，不讓整晚的反思炸掉。"""
    try:
        # content 傳給濾網時是原樣的，但濾網以 strip 後的長度判斷；落庫前補上 strip，
        # 免得守則帶著前後空白逐字進 system prompt。
        strategies.record(
            elder_id,
            candidate.content.strip(),
            candidate.category,
            candidate.evidence,
            candidate.observed_days,
            candidate.supersedes,
        )
    except StrategyError as exc:
        # 最常見的來源：反思讀完生效中守則後、寫入前，家屬在後台撤銷了取代對象。
        logger.warning(
            "守則寫入失敗，跳過此條 elder=%s 取代對象=%s 內容=%r 原因=%s",
            elder_id,
            candidate.supersedes,
            candidate.content,
            exc,
        )


def _build_prompt(
    logs: list[ReminderLog],
    adopted: list[Strategy],
    lookback_days: int,
    min_observed_days: int,
    max_strategies: int,
) -> str:
    # 回看天數必須明講：模型看得到對話、卻不知道這扇窗有多長。少了這一句，一個誠實但
    # 估錯的 observed_days=10 會被 `_split_forged_evidence` 判成「證據捏造」而丟掉——那是
    # 我們沒告訴它上界，不是它想繞過門檻。上下界要一起講，否則模型只知道下界（門檻）。
    return (
        REFLECTION_PROMPT
        + f"\n【回看範圍】本次回看 {lookback_days} 天的對話。"
        + f"observed_days 不得大於 {lookback_days}，超過者會被視為捏造證據而丟棄。\n"
        + f"\n【證據門檻】observed_days 少於 {min_observed_days} 的守則會被系統丟棄。\n"
        + "\n【這段期間的提醒與回應】\n"
        + _format_reminders(logs)
        + "\n\n【目前已生效的守則】\n"
        + _format_adopted(adopted, max_strategies)
    )


def _format_reminders(logs: list[ReminderLog]) -> str:
    if not logs:
        return "（這段期間沒有推送任何提醒）"
    lines = []
    for log in logs:
        answered = "有回應" if log.responded_at is not None else "沒有回應"
        lines.append(f"- [{log.kind}]{log.content}（長輩{answered}）")
    return "\n".join(lines)


def _format_adopted(adopted: list[Strategy], max_strategies: int) -> str:
    if not adopted:
        return f"（目前沒有任何守則；上限 {max_strategies} 條）"
    lines = "\n".join(f"- id={row.strategy_id}：{row.content}" for row in adopted)
    return (
        f"目前已有 {len(adopted)} 條守則（上限 {max_strategies} 條）：\n{lines}\n"
        "若已達上限而你認為新守則更重要，必須在 supersedes 欄填入要取代的那條 id；"
        "未指定取代對象的新守則會被丟棄。"
    )


def _parse(reply: str) -> list[Candidate] | None:
    """解析 LLM 回傳；任一環節不合格式即回 None（整批丟棄，不寫入任何守則）。"""
    try:
        raw = json.loads(_strip_code_fence(reply))
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, list):
        return None
    candidates = []
    for item in raw:
        candidate = _to_candidate(item)
        if candidate is None:
            return None
        candidates.append(candidate)
    return candidates


def _to_candidate(item: object) -> Candidate | None:
    """把一個 JSON 元素轉成 Candidate；欄位缺漏或型別救不回來時回 None（整批丟棄）。

    ## content 嚴格、observed_days 寬鬆——這個不對稱是刻意的，請不要「一致性重構」掉

    `observed_days` 接受 int-coercible（`"3"`、`3.0` → 3）。理由是失效模式的形狀：LLM 的
    JSON 序列化習慣是**穩定的**——會把數字加引號的模型，是每晚都加。所以嚴格版的代價
    不是「偶爾損失一晚」，而是這個功能可能**從上線第一天起就永遠學不到任何東西**，而
    唯一的訊號是每晚一行 warning。守則自動生效、無人審，沒有人會盯著「今晚沒新增守則」，
    因為那本來就是常態——這是靜默的全功能失效。轉型在此不損及任何一道防線：
    `observed_days` 只流向「與 `min_observed_days` 比大小」與 DB 的整數欄位，不參與醫療詞
    比對、不參與結構驗證、也不進 system prompt。

    `content` 則**必須維持嚴格**：`str(42)` 會製造出「42」這條守則——可印、單行、夠短、
    無醫療詞、分類合法，**四道濾網全部放行**，然後永久注入 system prompt。content 的語意
    有效性無法用轉型救回（一條守則要嘛是句人話、要嘛不是），`observed_days` 可以（一個
    數字加了引號還是同一個數字）。兩者的寬嚴之別來自「轉型能不能救回語意」，不是疏漏。

    非數字的 `observed_days`（「很多天」）仍整批丟棄：那是模型連題目都沒答對，其 content
    同樣不值得信任。
    """
    if not isinstance(item, dict) or any(field not in item for field in _REQUIRED_FIELDS):
        return None
    content, category = item["content"], item["category"]
    if not isinstance(content, str) or not isinstance(category, str):
        return None
    evidence = _to_evidence(item["evidence"])
    if evidence is None:
        return None
    observed_days = _to_observed_days(item["observed_days"])
    if observed_days is None:
        return None
    supersedes = item.get("supersedes")
    if isinstance(supersedes, str):
        supersedes = supersedes.strip() or None  # 模型常拿空字串代替 null，視為沒有取代對象。
    elif supersedes is not None:
        # 0／false／[] 等 falsy 值不是 null，是型別錯；`or None` 會讓它們靜默變成「沒有
        # 取代對象」，把一條本該丟棄的候選放進來。
        return None
    return Candidate(
        content=content,
        category=category,
        evidence=evidence,
        observed_days=observed_days,
        supersedes=supersedes,
    )


def _to_evidence(value: object) -> str | None:
    """evidence 允許字串或字串陣列（模型很常把觀察逐條列出）；其餘型別回 None。

    evidence 是四個欄位裡最無安全顧慮的——不進 system prompt、不參與任何一道濾網，只
    落庫供人回查。為了它的格式偏好丟掉整晚的反思，代價完全不成比例。
    """
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(line, str) for line in value):
        return "；".join(value)
    return None


def _to_observed_days(value: object) -> int | None:
    """轉成整數天數；bool 與非數字回 None。寬嚴之別的理由見 `_to_candidate`。"""
    # bool 必須先擋：它是 int 的子類（int(True) == 1），但 observed_days=true 的語意不是
    # 「觀察到 1 天」，而是模型根本沒在回答這個問題。
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, (float, str)):
        try:
            # 先轉 float 再取整，一併吃下 3.0 與 "3"／"3.0"。無條件捨去（3.7 → 3）只會
            # 低估天數、讓證據門檻更嚴，不可能放行證據不足的守則。
            number = float(value)
        except ValueError:
            return None  # 「很多天」這種答不出數字的回應，仍整批丟棄。
        return int(number) if math.isfinite(number) else None  # inf／nan 不是天數。
    return None


def _strip_code_fence(reply: str) -> str:
    """去掉模型偶爾加上的 markdown code fence（```json ... ```）。

    縱深防禦：response_schema 已約束輸出為乾淨 JSON，正常不會有 fence；此撈殼刻意
    保留，讓受控生成偶爾失常時仍能救回，而非整批丟棄一整晚的反思。
    """
    text = reply.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()[1:]  # 去掉 ``` 或 ```json 那一行
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()
