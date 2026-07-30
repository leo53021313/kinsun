"""分級＋審核合併分類器的離線測試：不碰 LLM、不碰 DB。

重心與 `test_safety_detector.py`／`test_safety_moderation.py` 對稱：
1. 呼叫失敗（LLMError）與內容解析失敗都必須雙重降級——風險面 fail-safe（保守
   偏高），審核面 fail-open（保守放行），絕不可讓安全檢查本身的失敗打斷對話。
2. `classify` 回傳的是**原始 LLM 判斷**，尚未套用關鍵詞地板／信心門檻——那兩層
   決策交給呼叫端的 `RiskDetector.combine_with_llm`／`AbuseModerator.
   apply_threshold`（見 `test_pipeline.py` 的合併路徑測試）。
"""

from kinsun.llm import LLMError, Message
from kinsun.safety.combined_classifier import (
    _COMBINED_SCHEMA,
    COMBINED_SYSTEM_PROMPT,
    CombinedSafetyResult,
    LlmCombinedSafetyClassifier,
    _parse_combined,
    failopen_moderation,
    failsafe_result,
)
from kinsun.safety.moderation import MODERATE_SYSTEM_PROMPT, AbuseCategory
from kinsun.safety.tiers import RiskTier

# ── _parse_combined：內容階段的失敗 ────────────────────────────────────


def test_parse_valid_json():
    r = _parse_combined(
        '{"tier": 2, "tier_confidence": 0.9, "tier_reason": "求救", '
        '"category": "role_hijack", "moderation_confidence": 0.8, '
        '"moderation_reason": "要求扮演"}'
    )
    assert r.risk.tier == RiskTier.L2
    assert r.risk.confidence == 0.9
    assert r.risk.reason == "求救"
    assert r.risk.signals == ["llm"]
    assert r.moderation.category is AbuseCategory.ROLE_HIJACK
    assert r.moderation.confidence == 0.8
    assert r.moderation.reason == "要求扮演"
    assert r.moderation.signals == ["llm"]


def test_parse_json_in_markdown_fence():
    r = _parse_combined(
        '```json\n{"tier": 0, "tier_confidence": 0.9, "tier_reason": "一般", '
        '"category": "none", "moderation_confidence": 0.9, '
        '"moderation_reason": "正常"}\n```'
    )
    assert r.risk.tier == RiskTier.L0
    assert r.moderation.category is AbuseCategory.NONE


def test_parse_clamps_tier_out_of_old_three_tier_range():
    """舊制吐 3 也夾回 L2（與 classifier._parse_classification 對稱）。"""
    r = _parse_combined(
        '{"tier": 3, "tier_confidence": 0.9, "tier_reason": "x", '
        '"category": "none", "moderation_confidence": 0.9, "moderation_reason": "x"}'
    )
    assert r.risk.tier == RiskTier.L2


def test_parse_clamps_confidence_out_of_range():
    r = _parse_combined(
        '{"tier": 1, "tier_confidence": 7.5, "tier_reason": "x", '
        '"category": "none", "moderation_confidence": -1, "moderation_reason": "x"}'
    )
    assert r.risk.confidence == 1.0
    assert r.moderation.confidence == 0.0


def test_parse_malformed_json_falls_back_to_dual_degradation():
    """**整段**讀不到 JSON 才雙重降級：風險面 fail-safe（L0）、審核面 fail-open（NONE）。"""
    r = _parse_combined("這不是 JSON")
    assert r == failsafe_result()
    assert r.risk.tier == RiskTier.L0
    assert "llm:error" in r.risk.signals
    assert r.moderation.category is AbuseCategory.NONE
    assert not r.moderation.is_blocked
    assert "llm:error" in r.moderation.signals


def test_parse_valid_json_that_is_not_an_object_falls_back():
    """合法 JSON 但不是物件（模型吐陣列）：兩半都真的沒有資料，雙重降級。"""
    assert _parse_combined("[1, 2, 3]") == failsafe_result()


# ── 兩半各自獨立降級（2026-07-30 審查 C-1）─────────────────────────────
#
# ⚠️ 這一組是本檔最重要的測試。合併之後 tier 與 category 來自同一份 JSON，把兩半包在
# 同一個 try 裡會讓一個**審核欄位**的格式失誤把**已經判對的 tier=2 一起丟掉**——
# 家屬因此收不到通知，而長輩照樣拿到正常回覆（審核 fail-open），線上完全無聲。


def test_bad_category_does_not_take_the_risk_tier_down_with_it():
    """`category` 吐列舉外的字串：審核半邊 fail-open，但 tier=2 必須存活。"""
    r = _parse_combined(
        '{"tier": 2, "tier_confidence": 0.95, "tier_reason": "跌倒", '
        '"category": "fall_risk", "moderation_confidence": 0.9, "moderation_reason": "x"}'
    )
    assert r.risk.tier == RiskTier.L2  # ← 這一行紅掉就代表家屬會漏收通知
    assert r.risk.confidence == 0.95
    assert r.risk.reason == "跌倒"
    assert r.risk.signals == ["llm"]
    assert r.moderation.category is AbuseCategory.NONE
    assert "llm:error" in r.moderation.signals


def test_null_moderation_confidence_does_not_take_the_risk_tier_down_with_it():
    """`moderation_confidence` 吐 null（`float(None)` → TypeError）同理。"""
    r = _parse_combined(
        '{"tier": 2, "tier_confidence": 0.9, "tier_reason": "胸悶", '
        '"category": "none", "moderation_confidence": null, "moderation_reason": "x"}'
    )
    assert r.risk.tier == RiskTier.L2
    assert r.moderation.category is AbuseCategory.NONE
    assert "llm:error" in r.moderation.signals


def test_missing_category_keeps_the_risk_half():
    """缺 `category`：審核半邊 fail-open，風險半邊照原樣（tier=1 不該被丟成 L0）。"""
    r = _parse_combined('{"tier": 1, "tier_confidence": 0.5, "tier_reason": "睡不好"}')
    assert r.risk.tier == RiskTier.L1
    assert r.risk.signals == ["llm"]
    assert r.moderation == failopen_moderation()


def test_bad_tier_does_not_take_the_moderation_half_down_with_it():
    """反方向也要成立：`tier` 壞掉時審核半邊的判斷照樣留下（對稱性）。"""
    r = _parse_combined(
        '{"tier": "很嚴重", "category": "role_hijack", '
        '"moderation_confidence": 0.95, "moderation_reason": "要求扮演"}'
    )
    assert r.risk.tier == RiskTier.L0
    assert "llm:error" in r.risk.signals
    assert r.moderation.category is AbuseCategory.ROLE_HIJACK
    assert r.moderation.confidence == 0.95
    assert r.moderation.signals == ["llm"]


# ── LlmCombinedSafetyClassifier：呼叫階段的失敗 ─────────────────────────


class _BoomLLM:
    def generate(self, *, system_prompt: str, messages: list[Message], response_schema=None) -> str:
        raise LLMError("boom")


def test_classifier_dual_degrades_on_llm_error():
    r = LlmCombinedSafetyClassifier(_BoomLLM()).classify("我不想活了")
    assert r.risk.tier == RiskTier.L0
    assert "llm:error" in r.risk.signals
    assert r.moderation.category is AbuseCategory.NONE
    assert "llm:error" in r.moderation.signals


def test_classify_requests_structured_output_with_the_combined_schema():
    captured = {}

    class _CapturingLLM:
        def generate(self, *, system_prompt, messages, response_schema=None):
            captured["schema"] = response_schema
            captured["system_prompt"] = system_prompt
            captured["text"] = messages[-1].content
            return (
                '{"tier": 0, "tier_confidence": 0.9, "tier_reason": "ok", '
                '"category": "none", "moderation_confidence": 0.9, "moderation_reason": "ok"}'
            )

    result = LlmCombinedSafetyClassifier(_CapturingLLM()).classify("你好")
    assert captured["schema"] == _COMBINED_SCHEMA
    assert captured["system_prompt"] == COMBINED_SYSTEM_PROMPT
    assert captured["text"] == "你好"
    assert isinstance(result, CombinedSafetyResult)


def test_schema_constrains_category_to_the_enum():
    """受控生成先擋一層列舉外的 category（縱深防禦，2026-07-30 審查）。"""
    assert _COMBINED_SCHEMA["properties"]["category"]["enum"] == [
        "none",
        "role_hijack",
        "system_disclosure",
        "code_generation",
    ]


# ── 提示詞不得漏抄（2026-07-30 審查 M-3）───────────────────────────────


def test_combined_prompt_keeps_every_moderation_exception_verbatim():
    """審核那六條「一律判 none」例外清單是防止誤攔危急語句的核心，逐條逐字比對。

    合併提示詞是把兩份既有提示詞抄在一起，最容易出的錯就是抄漏一條——而漏掉第 1、2
    條的後果是長輩講「我不想活了」被判成違規、整輪跳過 agent，家屬那條路雖然仍會
    通報（審核排在通報之後），但長輩會拿到一句莫名的回絕話術。
    """
    exceptions = [
        line.strip()
        for line in MODERATE_SYSTEM_PROMPT.splitlines()
        if line.strip() and line.strip()[0].isdigit() and "." in line[:3]
    ]
    assert len(exceptions) == 6, "來源提示詞的例外條數變了，本測試需同步"
    for exception in exceptions:
        assert exception in COMBINED_SYSTEM_PROMPT, f"合併提示詞漏抄：{exception}"


def test_combined_prompt_keeps_the_bold_emphasis_on_the_critical_rule():
    """整份提示詞最安全關鍵的一句話，強調標記不可掉（審查 M-3a）。"""
    assert "**一律判 none**" in COMBINED_SYSTEM_PROMPT


def test_combined_prompt_states_the_two_judgements_are_independent():
    """必須明講兩件事互不影響——否則模型可能拿審核結論去條件化 tier（審查 M-3）。

    兩個方向都要講到：審核段講「危急句也可以是 category=none」，分級段講「審核結論
    不可影響 tier」。只寫一邊時，模型仍可能從另一個方向把兩者綁在一起。
    """
    assert "一句話可以同時是「危急」又是「category=none」" in COMBINED_SYSTEM_PROMPT
    assert "不論審核結論是什麼，都不可以影響 tier 的判定" in COMBINED_SYSTEM_PROMPT
