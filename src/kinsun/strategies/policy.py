"""守則的三道濾網：醫療黑名單、證據門檻、上限與取代。

守則自動生效（無人審），擋住壞守則的就只剩這裡。第一道尤其重要——反思的
prompt 雖已明文禁止產出醫療類守則，但**不能信任模型會乖乖聽話**，程式碼必須
自己再擋一次。金孫可以學會不叫長輩阿婆，但永遠不准學會不提醒她吃藥。

本詞表刻意與 rag/answer_policy.py 的 _MEDICAL_ACTION_TERMS 分開維護：兩者用途
不同（那邊擋 RAG 回答、這邊擋守則），共用常數會讓兩邊互相牽動。
"""

from __future__ import annotations

from dataclasses import dataclass

from kinsun.strategies.models import STRATEGY_CATEGORIES

# 醫療動作詞：守則內容命中任一即丟棄。寧可錯殺，不可放行。
#
# 詞表原則：優先收「最短且無歧義的詞素」，而非窮舉複合詞——窮舉的失效模式是漏掉
# 沒想到的組合（列了「疼痛」卻漏掉「頭痛」，一句「她說頭痛只是想撒嬌，不用理會」
# 就會放行）。單字詞素會連未預期的複合詞一起攔下，這正是我們要的。
#
# 反向的紅線同樣重要：詞表不得吃掉日常語彙（關心、身體、精神、心情），否則語氣、
# 稱呼、話題、作息這四類合法守則永遠生不出來，功能等於廢掉。因此刻意**不收**
# 「急」（會誤殺「不用急著回她」）、「傷」（會誤殺「傷心」）、「昏」（會誤殺
# 「黃昏」）、「針」（會誤殺「針對」），改以完整詞收錄。
_MEDICAL_TERMS = (
    # 用藥：「藥」涵蓋吃藥、用藥、停藥、藥量、降血壓藥、藥師。
    "藥",
    "劑量",
    "服用",
    "打針",
    "注射",
    "胰島素",
    "疫苗",
    # 就醫與醫療處置：「醫」涵蓋醫生、醫師、就醫、送醫、醫院；
    # 「診」涵蓋門診、回診、急診、診斷、診所。
    "醫",
    "診",
    "掛號",
    "護理師",
    "健保卡",
    "住院",
    "開刀",
    "手術",
    "復健",
    "洗腎",
    "化療",
    "救護車",
    "119",
    "急救",
    # 身體狀況與生理數值：「血」涵蓋血壓、血糖、血氧、出血、貧血；
    # 「痛」涵蓋疼痛、頭痛、胃痛、痛風；「病」涵蓋生病、病情、疾病、慢性病。
    "血",
    "痛",
    "病",
    "喘",
    "咳",
    "暈",
    "昏倒",
    "昏迷",
    "呼吸",
    "心跳",
    "體溫",
    "發燒",
    "跌",
    "受傷",
    "傷口",
    "過敏",
    "症狀",
    "不舒服",
    "失智",
    "中風",
    "癌",
    # 危急
    "危急",
    "緊急",
    "求救",
)


@dataclass(frozen=True)
class Candidate:
    """反思產出的候選守則（尚未過濾）。"""

    content: str
    category: str
    evidence: str
    observed_days: int
    supersedes: str | None


def is_admissible(
    candidate: Candidate,
    *,
    min_observed_days: int,
    adopted_count: int,
    max_strategies: int,
    adopted_ids: set[str],
) -> str | None:
    """通過回 None；未通過回一句中文拒絕理由（供 log）。"""
    if candidate.category not in STRATEGY_CATEGORIES:
        return f"分類不在白名單內：{candidate.category}"
    hit = next((t for t in _MEDICAL_TERMS if t in candidate.content), None)
    if hit is not None:
        return f"醫療相關內容不得成為守則（命中「{hit}」）"
    if candidate.observed_days < min_observed_days:
        return f"證據不足：只觀察到 {candidate.observed_days} 天，需 {min_observed_days} 天"
    if candidate.supersedes is not None and candidate.supersedes not in adopted_ids:
        return f"要取代的守則不存在或未生效：{candidate.supersedes}"
    if adopted_count >= max_strategies and candidate.supersedes is None:
        return f"已達守則上限（{max_strategies}）且未指定取代對象"
    return None
