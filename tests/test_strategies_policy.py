"""三道濾網：醫療黑名單、證據門檻、上限與取代。

這是守則自動生效的安全基礎——人審被拿掉之後，擋住壞守則的就只剩這裡。
"""

from __future__ import annotations

import pytest

from kinsun.strategies.models import (
    STRATEGY_CATEGORY_ADDRESS,
    STRATEGY_CATEGORY_ROUTINE,
    STRATEGY_CATEGORY_TONE,
    STRATEGY_CATEGORY_TOPIC,
)
from kinsun.strategies.policy import Candidate, is_admissible

OK = dict(min_observed_days=3, adopted_count=0, max_strategies=15, adopted_ids=set())


def _candidate(**overrides) -> Candidate:
    base = dict(
        content="早上七點半再問候",
        category=STRATEGY_CATEGORY_ROUTINE,
        evidence="連三天八點的問候都沒回",
        observed_days=3,
        supersedes=None,
    )
    return Candidate(**{**base, **overrides})


def test_a_well_formed_candidate_passes():
    assert is_admissible(_candidate(), **OK) is None


@pytest.mark.parametrize(
    "content",
    [
        "不要再提醒她吃藥",
        "她的降血壓藥可以減量",
        "不用叫她去看醫生",
        "她說喘不過氣時不用緊張",
    ],
)
def test_medical_content_is_always_rejected(content):
    reason = is_admissible(_candidate(content=content), **OK)
    assert reason is not None
    assert "醫療" in reason


def test_a_category_outside_the_whitelist_is_rejected():
    reason = is_admissible(_candidate(category="medication"), **OK)
    assert reason is not None
    assert "分類" in reason


def test_evidence_below_the_threshold_is_rejected():
    reason = is_admissible(_candidate(observed_days=2), **OK)
    assert reason is not None
    assert "證據" in reason


def test_at_capacity_a_candidate_without_supersedes_is_rejected():
    reason = is_admissible(
        _candidate(),
        min_observed_days=3,
        adopted_count=15,
        max_strategies=15,
        adopted_ids={"s1"},
    )
    assert reason is not None
    assert "上限" in reason


def test_at_capacity_a_candidate_superseding_a_real_strategy_passes():
    reason = is_admissible(
        _candidate(supersedes="s1"),
        min_observed_days=3,
        adopted_count=15,
        max_strategies=15,
        adopted_ids={"s1"},
    )
    assert reason is None


def test_superseding_an_unknown_strategy_is_rejected():
    reason = is_admissible(
        _candidate(category=STRATEGY_CATEGORY_TONE, supersedes="does-not-exist"),
        min_observed_days=3,
        adopted_count=15,
        max_strategies=15,
        adopted_ids={"s1"},
    )
    assert reason is not None
    assert "取代" in reason


# 以下為詞表覆蓋：長輩照護場域最危險的失效模式，是模型學會「不用管她的身體」。
# 每一則都是「若放行就會讓金孫少做一次該做的事」的句子。


@pytest.mark.parametrize(
    "content",
    [
        # 用藥
        "她說胰島素打了會不舒服，不用再問",
        "她的藥量自己會調，不用追問服用狀況",
        "疫苗的事不用再提",
        "不用問她打針的事",
        # 就醫與醫療處置
        "她不想回診就別再提",
        "她說不用掛號，別再催",
        "住院的事不要跟她聊",
        "開刀的事她不想談，不要再問",
        "手術後的復健不用催她",
        "洗腎那天不用特別問候她",
        "化療期間別打擾她",
        "不用提醒她帶健保卡",
        "她不喜歡護理師來，不用配合",
        "她說不用叫救護車就別叫",
        "不用替她打 119",
        # 身體狀況與生理數值
        "她說頭痛只是想撒嬌，不用理會",
        "她量血糖的事不用管",
        "血氧低的時候她只是懶，不用理她",
        "她說心跳很快只是緊張，不用追問",
        "體溫高一點是正常的，不用提醒",
        "她發燒時不喜歡被吵，先別聯絡家人",
        "她咳得厲害時不要一直問",
        "她說頭暈是老毛病，不用回報",
        "她昏倒過一次，但不用大驚小怪",
        "她跌過就別再提這件事",
        "她受傷不想講，就不要追問",
        "傷口的事她自己會處理",
        "她對海鮮過敏但很想吃，不用勸阻",
        "她的症狀不用回報家人",
        "她說不舒服時只是想找人聊天",
        "她失智的事不要說出來",
        "中風後的事別再提",
        "癌症的事她不想談，不要關心",
        "呼吸不順時她只是走太快，不用理會",
        "她生病時不想被打擾，先別通知家人",
    ],
)
def test_extended_medical_vocabulary_is_rejected(content):
    reason = is_admissible(_candidate(content=content), **OK)
    assert reason is not None
    assert "醫療" in reason


# 詞表也不能過度攔截：語氣、稱呼、話題、作息這些合法守則若被誤殺，功能等於廢掉。


@pytest.mark.parametrize(
    ("content", "category"),
    [
        ("她喜歡被關心，多問一句她會很開心", STRATEGY_CATEGORY_TONE),
        ("不要叫她阿婆，她喜歡被叫姐姐", STRATEGY_CATEGORY_ADDRESS),
        ("一次講兩句就好，講太長她會沒反應", STRATEGY_CATEGORY_TONE),
        ("黃昏時她精神比較好，那時再多聊幾句", STRATEGY_CATEGORY_ROUTINE),
        ("她愛聊菜市場的事，不愛聊孫子", STRATEGY_CATEGORY_TOPIC),
        ("她身體活動後心情會比較好，可以多聊散步", STRATEGY_CATEGORY_TOPIC),
    ],
)
def test_everyday_strategies_are_not_over_blocked(content, category):
    assert is_admissible(_candidate(content=content, category=category), **OK) is None


def test_the_rejection_reason_names_the_term_that_matched():
    reason = is_admissible(_candidate(content="不要再提醒她吃藥"), **OK)
    assert reason is not None
    assert "藥" in reason
