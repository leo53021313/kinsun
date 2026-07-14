"""每晚反思：讀過去 N 天的互動，沉澱出「這位長輩的相處之道」。

與 `reports/summaries.py` 的 `summarize_day` 是姊妹批次，但有兩個關鍵差異：

1. 讀「過去 N 天」而非只讀昨天——證據門檻（`policy.is_admissible`）要求守則跨多天
   重複出現，反思就必須看得到多天。照抄 `previous_day()` 會讓模型永遠只有一天的
   觀察可引用，門檻不是變嚴、而是整個功能失效。
2. 產出寫回系統自己（strategies 表 → 注入 system prompt），而非寫給家屬看。
   摘要是報告，反思是學習。

## 三個「壞掉也不能炸」的地方

守則自動生效、無人審，而這支批次每晚對每位長輩跑一次。它的失敗模式必須是
「今晚少學一條」，不能是「今晚整批長輩的反思都掛掉」：

* **回傳格式不合** → 整批丟棄並記 warning。半份 JSON 裡挑得出來的那幾條，來源同樣
  不可信；寧可今晚不學，不可學進垃圾。
* **單條被濾網擋下** → 只丟該條，其餘照寫。拒絕理由**逐條**記 warning：這是我們
  唯一能觀測「詞表誤殺了什麼」與「模型多常試圖越界」的訊號，揉成一句聚合日誌
  就再也分不出醫療攔截、注入攔截、證據不足、撞上限各發生幾次。
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
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from kinsun.llm import Message
from kinsun.memory.shortterm import MemoryStore, previous_day_bounds
from kinsun.reports.reminders import ReminderLog, ReminderLogStore
from kinsun.strategies.models import STRATEGY_STATUS_ADOPTED, Strategy
from kinsun.strategies.policy import MAX_CONTENT_CHARS, Candidate, admit_all
from kinsun.strategies.store import StrategyError, StrategyStore

logger = logging.getLogger("kinsun.strategies.reflection")

_SECONDS_PER_DAY = 86400.0  # 台灣無日光節約，一天固定 86400 秒。

_REQUIRED_FIELDS = ("content", "category", "evidence", "observed_days")

# 反思的系統提示。第 3、4 條是對濾網的「事前緩解」而非重複防護：
# 濾網（policy.py）會擋掉含醫療字眼與過長／多行的守則，但它只能丟棄、無法改寫，
# 合法的話題類守則（「不要聊她過世老伴生病的那段」）因此會被誤殺。與其放寬詞表，
# 不如在這裡就要求模型寫成不含醫療字眼的說法。長度上限引用 policy 的公開常數，
# 兩邊永遠一致。
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
    f"4. 每條守則都是一句話，不超過 {MAX_CONTENT_CHARS} 個字；不可換行、不可分點、"
    "不可加標題。\n"
    "5. 每條守則必須有跨多天、重複出現的證據。單一天的一次觀察不算數"
    "（長輩可能只是那天心情不好），此類一律不要產出。\n"
    "6. 已經生效的守則不要重複產出。\n\n"
    "【回傳格式】只回傳 JSON 陣列，不要任何其他文字或 markdown 標記。每個元素：\n"
    '{"content": "一句話的守則", "category": "四類之一", '
    '"evidence": "你依據的觀察", "observed_days": 這個模式在幾天中出現過的整數, '
    '"supersedes": null 或要取代的既有守則 id}\n'
    "沒有值得沉澱的守則時，回傳空陣列 []。\n"
)


class Reflector(Protocol):
    """反思用的 LLM 呼叫端；形狀同 `summarize_day` 的 summarizer（見 llm.LLMClient）。"""

    def generate(self, *, system_prompt: str, messages: list[Message]) -> str: ...


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
) -> None:
    """反思這位長輩過去 lookback_days 天的互動，把通過濾網的守則寫成生效中的守則。"""
    # 迄點＝今日零時：只反思已完整結束的日子，今天才過幾小時的片段不算一天。
    _, end = previous_day_bounds(clock())
    start = end - lookback_days * _SECONDS_PER_DAY
    turns = short_term.list_for_range(elder_id, start=start, end=end)
    if not turns:
        return

    logs = reminder_logs.list_for_range(elder_id, start=start, end=end)
    adopted = strategies.list_for_elder(elder_id, status=STRATEGY_STATUS_ADOPTED)
    system_prompt = _build_prompt(logs, adopted, min_observed_days, max_strategies)
    reply = reflector.generate(system_prompt=system_prompt, messages=turns)

    candidates = _parse(reply)
    if candidates is None:
        # 整批丟棄：格式壞掉代表這份回應的來源不可信，挑得出來的那幾條同樣不可信。
        logger.warning("反思回傳格式不合，整批丟棄 elder=%s 回應=%r", elder_id, reply[:200])
        return

    accepted, rejected = admit_all(
        candidates,
        min_observed_days=min_observed_days,
        adopted_count=len(adopted),
        max_strategies=max_strategies,
        adopted_ids={row.strategy_id for row in adopted},
    )
    for candidate, reason in rejected:
        # 逐條記錄、理由原文照登：理由字串本身就是分類（醫療攔截／結構驗證／證據不足／
        # 撞上限），聚合成一句就失去可分類統計的價值。
        logger.warning(
            "守則被濾網擋下 elder=%s 理由=%s 分類=%s 內容=%r",
            elder_id,
            reason,
            candidate.category,
            candidate.content,
        )
    for candidate in accepted:
        _record(strategies, elder_id, candidate)


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
    min_observed_days: int,
    max_strategies: int,
) -> str:
    return (
        REFLECTION_PROMPT
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
    """把一個 JSON 元素轉成 Candidate；欄位缺漏或型別不對回 None。

    型別嚴格（不做 str()／int() 強制轉型）：能寫出 observed_days="很多天" 的回應，
    其 content 同樣不值得信任。內容的合法性交給濾網，此處只認格式。
    """
    if not isinstance(item, dict) or any(field not in item for field in _REQUIRED_FIELDS):
        return None
    content, category, evidence = item["content"], item["category"], item["evidence"]
    if not all(isinstance(value, str) for value in (content, category, evidence)):
        return None
    observed_days = item["observed_days"]
    # bool 是 int 的子類，得另外擋掉：observed_days=true 不是「觀察到 1 天」。
    if isinstance(observed_days, bool) or not isinstance(observed_days, int):
        return None
    supersedes = item.get("supersedes") or None  # 模型常填空字串代替 null。
    if supersedes is not None and not isinstance(supersedes, str):
        return None
    return Candidate(
        content=content,
        category=category,
        evidence=evidence,
        observed_days=observed_days,
        supersedes=supersedes,
    )


def _strip_code_fence(reply: str) -> str:
    """去掉模型偶爾加上的 markdown code fence（```json ... ```）。"""
    text = reply.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()[1:]  # 去掉 ``` 或 ```json 那一行
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()
