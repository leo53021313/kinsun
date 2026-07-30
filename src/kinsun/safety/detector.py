"""危急偵測：合併關鍵詞與 LLM，後端複核 → RiskAssessment。"""

from __future__ import annotations

from kinsun.safety.classifier import RiskClassifier
from kinsun.safety.keywords import classify_keywords
from kinsun.safety.tiers import FAILSAFE_EVENT_REASON, RiskAssessment, RiskTier


class RiskDetector:
    """三級制（✅ D-72，己-4）：關鍵詞層是**地板**，分級器只能往上加、不能往下拉。

    ## 為什麼把「症狀詞翻案」整段移除（2026-07-30）

    翻案是 2026-07-26 為了修四種誤報而加的——字面比對讀不懂否定、時態與主詞，
    而分級器讀得懂，所以讓有把握的分級器把症狀詞從 L2 降到 L1：

    | 長輩說的話 | 為什麼會誤報 |
    | --- | --- |
    | 你放心啦，我沒有跌倒，好好的 | 讀不懂否定 |
    | 我十年前跌倒過一次，現在都好了 | 讀不懂時態 |
    | 隔壁的陳太太昨天跌倒送醫院了 | 讀不懂主詞 |
    | 老人家要怎麼預防跌倒？ | 讀不懂這是提問 |

    這四種誤報現在由 `keywords.classify_keywords`（地端偵測器）在**比對當下**就擋掉，
    否定／人稱／引述／時態四層守門是確定性的規則，不需要等分級器事後補救。
    四句話在新的關鍵詞層全部判 L0，翻案已無事可翻。

    移除它換回三件事：

    1. **降級只剩一條路，安全行為可以一眼看完。** 兩條降級路徑並存時，
       「這句話為什麼沒通知家屬」要交叉比對關鍵詞層、分級器信心與 `llm:error`
       三個變數；現在只剩「分級器自己判 L2 但沒把握」這一種。
    2. **不再把安全地板的存廢交給一個機率性系統。** 實測同一句話、同一個模型
       連跑兩次約有一成判定不同，換模型版本再變 6%——那正好是通知線兩側。
       翻案門檻拉到 0.7 只是降低機率，不是消除它。
    3. **誤報的修法從「事後翻案」變成「當下就不觸發」**，兩者對家屬的差別是
       「收到通知再被降級為留痕」vs「根本不會產生這筆事件」。

    保留的兩條路徑，語意都不是「推翻關鍵詞層」：

    * **純分級器的 L2 信心不足降 L1**（`kw_tier < L2` 才適用）——降的是分級器
      自己的判定，關鍵詞地板碰不到。
    * **`llm:error` fail-safe**（✅ D-31 甲-5）——分級器故障時保守記 L1 留痕。

    ## 關鍵詞層換成地端偵測器的實測（2026-07-30）

    kinsun 60 句標注集：應通報漏 13→**6**，不該通報卻報 7→**1**。
    219 句兩邊都沒看過的真危機語料：接住 7.3%→**68.5%**。
    代價是真人語料誤報 0.09%→0.37%（6,691 句）、0.58%→1.37%（1,895 句）。
    """

    def __init__(
        self,
        classifier: RiskClassifier,
        *,
        mid: float = 0.4,
    ) -> None:
        self._classifier = classifier
        self._mid = mid

    def assess(self, text: str) -> RiskAssessment:
        try:
            llm = self._classifier.classify(text)
        except Exception:  # noqa: BLE001 - 偵測絕不可中斷對話
            llm = RiskAssessment(RiskTier.L0, 0.0, "分級器例外", ["llm:error"])
        return self.combine_with_llm(text, llm)

    def combine_with_llm(self, text: str, llm: RiskAssessment) -> RiskAssessment:
        """把關鍵詞地板與**已經取得**的 LLM 判斷合併成最終分級。

        獨立成方法（2026-07-30 延遲優化 C2）：分級與審核合併成一次 Gemini 呼叫時，
        呼叫端已經有現成的 `llm` 判斷（不必也不該再呼叫 `self._classifier`），只需要
        套用與 `assess()` 完全相同的關鍵詞地板／降級規則——兩條路徑必須共用同一份
        決策邏輯，不可各寫一份，否則遲早會分岔。
        """
        kw_tier, kw_emergency = classify_keywords(text)
        signals: list[str] = []
        if kw_tier > RiskTier.L0:
            # `keyword:emergency` 只影響家屬簡訊要不要附 119 提示（notifier._format_alert），
            # 不再有「不得翻案」的語意——翻案機制已移除，見類別 docstring。
            signals.append("keyword:emergency" if kw_emergency else "keyword:symptom")
        signals.extend(llm.signals)

        final = max(kw_tier, llm.tier)
        # 唯一的降級路徑：分級器自己判 L2 但沒把握。`kw_tier < L2` 這個條件是關鍵——
        # 它保證這條路徑碰不到關鍵詞層撐起來的地板，降的永遠只是分級器自己的判定。
        if final == RiskTier.L2 and llm.confidence < self._mid and kw_tier < RiskTier.L2:
            final = RiskTier.L1
        # 關鍵詞撐住的等級遇分級器故障（✅ 庚-41／A-44）：reason 反映真正觸發原因
        # ——reason 進 risk_events 留痕與每日摘要，寫「分級器例外」會誤導。
        # （家屬通知文案自 2026-07-29 起只引長輩原話，不再取 reason。）
        if "llm:error" in llm.signals and kw_tier >= final > RiskTier.L0:
            return RiskAssessment(final, llm.confidence, "命中症狀詞（分級器故障期間）", signals)
        # ✅ D-31（甲-5）fail-safe：分級器故障（例外或回傳無法解析）且句子非空時，
        # 不再靜默 L0——保守記 L1 供留痕（pipeline 落庫不通知）。關鍵詞命中者不受影響。
        if "llm:error" in llm.signals and text.strip() and final < RiskTier.L1:
            return RiskAssessment(RiskTier.L1, 0.0, FAILSAFE_EVENT_REASON, signals)
        return RiskAssessment(final, llm.confidence, llm.reason, signals)
