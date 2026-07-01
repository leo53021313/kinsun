from kinsun.longterm import provenance


def test_constants_and_labels():
    assert provenance.SELF_CLAIMED == "self_claimed"
    assert provenance.label(provenance.SELF_CLAIMED) == "長者自述"
    assert provenance.label(provenance.FAMILY_CONFIRMED) == "家屬確認"


def test_unknown_label_falls_back():
    assert provenance.label("???") == "未標註"


def test_custom_prompt_mentions_self_claim_discipline():
    assert "自述" in provenance.CUSTOM_FACT_EXTRACTION_PROMPT
    assert "診斷" in provenance.CUSTOM_FACT_EXTRACTION_PROMPT


def test_custom_prompt_requires_traditional_chinese_output():
    """抽取出的記憶須用台灣繁體中文，避免 mem0 預設輸出英文。"""
    assert "繁體中文" in provenance.CUSTOM_FACT_EXTRACTION_PROMPT
