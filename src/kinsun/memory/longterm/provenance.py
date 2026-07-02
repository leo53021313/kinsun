"""記憶來源可信度（provenance）常數、中文標註與抽取紀律 prompt。"""

from __future__ import annotations

SELF_CLAIMED = "self_claimed"  # 長者自述
INFERRED = "inferred"  # 推測
FAMILY_CONFIRMED = "family_confirmed"  # 家屬確認

LABELS = {
    SELF_CLAIMED: "長者自述",
    INFERRED: "推測",
    FAMILY_CONFIRMED: "家屬確認",
}


def label(provenance: str) -> str:
    return LABELS.get(provenance, "未標註")


CUSTOM_FACT_EXTRACTION_PROMPT = (
    "你負責從長者與「金孫」的對話中，抽取對長期照護有意義的穩定事實"
    "（個資、家庭、用藥、慢性病、重要事件）。請遵守：\n"
    "1. 健康宣稱若僅為長者自述、未經醫療或家屬確認，視為未確認，不可當成已確診的醫療事實。\n"
    "2. 不替長者下任何醫療診斷或用藥劑量判斷。\n"
    "3. 對認知退化者前後矛盾或可能記錯之處，不爭辯、不臆造為事實。\n"
    "4. 只抽取明確、穩定、可長期參考的資訊；閒聊與情緒由系統另行處理。\n"
    "5. 抽取出的每一條記憶內容一律以台灣繁體中文書寫（即使對話含其他語言）。\n"
    "請依框架要求輸出 JSON。"
)
