"""危急偵測：合併關鍵詞與 LLM，後端複核 → RiskAssessment。"""

from __future__ import annotations

from kinsun.safety.classifier import RiskClassifier
from kinsun.safety.keywords import classify_keywords
from kinsun.safety.tiers import FAILSAFE_EVENT_REASON, RiskAssessment, RiskTier

# 翻掉症狀詞這道安全地板所需的信心；刻意高於 `mid`（見 RiskDetector docstring）。
# 與 `safety_moderation_min_confidence` 同值同理由：關掉一道安全機制要比啟動它更難。
_OVERTURN_MIN_CONFIDENCE = 0.7


class RiskDetector:
    """三級制（✅ D-72，己-4）：單一降級門檻 mid——純 LLM 判 L2 但信心不足降 L1；
    **絕對詞**撐住的 L2 不受門檻影響。

    ## 症狀詞為什麼可以被有把握的分級器翻案（2026-07-26）

    症狀詞是字面比對，看不懂否定、時態與主詞。全流程模擬實測抓到四種必然誤報，
    而且誤報**真的送到家屬手機**（12 筆風險事件有 4 筆是假的）：

    | 長輩說的話 | 分級器自己寫的理由 | 舊行為 |
    | --- | --- | --- |
    | 你放心啦，我沒有跌倒，好好的 | 明確表示沒有跌倒且身體狀況良好 | L2 通報 |
    | 我十年前跌倒過一次，現在都好了 | 十年前的舊傷且已痊癒 | L2 通報 |
    | 隔壁的陳太太昨天跌倒送醫院了 | 描述鄰居的狀況，並非自身 | L2 通報 |
    | 老人家要怎麼預防跌倒？ | 一般健康衛教諮詢，無立即危險 | L2 通報 |

    三分之一的警報是假的，家屬看到的文案又與真警報一模一樣——狼來了會讓真的那次被忽略。

    故症狀詞改為：**分級器成功回覆、判定為 L0（完全沒事）、且信心達門檻時，降為 L1**
    （落庫留痕、不通知）。專案標注集實測（`data/safety_eval/labeled_utterances.jsonl`，
    60 句、應通報 27 句，真 Gemini 逐句判定後把同一份判定套新舊兩套規則）：

    | | 舊規則 | 新規則 |
    | --- | --- | --- |
    | 應通報 27 句，漏掉 | 0 | **0**（一句都沒掉） |
    | 不該通報 33 句，誤報 | 7 | **3**（剩下三筆全是絕對詞造成，見下） |

    真危急時分級器自己就判 L2（實測信心 0.99–1.00），關鍵詞地板是多餘的；
    它唯一真正有價值的時刻是分級器故障，而那條路徑一字未改。

    三條紅線一步都沒動：
    * **絕對詞**（想不開、喘不過氣、叫救護車…）仍然無條件 L2，不看分級器臉色。
    * **分級器故障**（`llm:error`）時，症狀詞照舊撐 L2——fail-safe 一字未改。
      （由 `test_a_broken_classifier_cannot_overturn_a_symptom_keyword_even_if_it_sounds_sure`
      守住：故障時回傳的 confidence 是垃圾值，不看 signals 就會被它騙過去。）
    * **信心不足**時不准翻案，維持原本的保守判定。

    ⚠️ 翻案的信心門檻（`overturn_min_confidence`）**刻意高於** `mid`，理由與
    `safety_moderation_min_confidence` 同源：兩個方向的代價不對稱。`mid` 管的是
    「要不要相信一個 L2 判定」，猜錯只是多吵家屬一次；這裡管的是「要不要把已經
    亮起的安全地板關掉」，猜錯就是漏掉一次真的求救。實測的誤報信心都在 0.90–1.00，
    把門檻拉高不影響修復效果，只是把「勉強及格的把握」擋在外面。
    """

    def __init__(
        self,
        classifier: RiskClassifier,
        *,
        mid: float = 0.4,
        overturn_min_confidence: float = _OVERTURN_MIN_CONFIDENCE,
    ) -> None:
        self._classifier = classifier
        self._mid = mid
        self._overturn_min = overturn_min_confidence

    def assess(self, text: str) -> RiskAssessment:
        kw_tier, kw_absolute = classify_keywords(text)
        try:
            llm = self._classifier.classify(text)
        except Exception:  # noqa: BLE001 - 偵測絕不可中斷對話
            llm = RiskAssessment(RiskTier.L0, 0.0, "分級器例外", ["llm:error"])

        signals: list[str] = []
        if kw_tier > RiskTier.L0:
            signals.append("keyword:absolute" if kw_absolute else "keyword:symptom")
        signals.extend(llm.signals)

        if kw_absolute:
            return RiskAssessment(RiskTier.L2, llm.confidence, "命中絕對危急詞", signals)

        final = max(kw_tier, llm.tier)
        if final == RiskTier.L2 and llm.confidence < self._mid and kw_tier < RiskTier.L2:
            final = RiskTier.L1
        # 症狀詞翻案（2026-07-26 全流程模擬實測，見類別 docstring）：字面比對讀不懂
        # 「我沒有跌倒」「十年前跌倒過」「隔壁陳太太跌倒」「怎麼預防跌倒」，而分級器讀得懂。
        # 只在它**沒故障、有把握、且判定低於 L2** 時才准翻，翻到 L1 而非 L0——
        # 長輩確實提到了症狀詞，這件事要留在每日摘要裡給家人看見，只是不必即刻響警報。
        # （不必再檢查 kw_absolute：絕對詞在上面就 return 了，走到這裡必為 False。）
        # ⚠️ 只准 `L0` 翻案，不准 `L1`：L1 的語意是「分級器自己也覺得有小訊號」，
        # 那正是不該把家屬通知拿掉的時候。標注集實測（60 句、應通報 27 句）證明這個
        # 分別是實的——允許 L1 翻案會新漏掉「我好幾天沒睡，眼睛都花了」與
        # 「最近都沒力氣，連菜都提不動」兩句（分級器判 L1／信心 0.90–0.95）；
        # 收緊成只准 L0 之後，**應通報的 27 句一句都沒掉**，誤報照樣從 7 降到 3。
        elif (
            kw_tier is RiskTier.L2
            and "llm:error" not in llm.signals
            and llm.tier is RiskTier.L0
            and llm.confidence >= self._overturn_min
        ):
            final = RiskTier.L1  # llm.tier 已保證 < L2，一律落在留痕層
        # 症狀詞撐住的等級遇分級器故障（✅ 庚-41／A-44）：reason 反映真正觸發原因
        # ——家屬通知文案取 reason，寫「分級器例外」會誤導。
        if "llm:error" in llm.signals and kw_tier >= final > RiskTier.L0:
            return RiskAssessment(final, llm.confidence, "命中症狀詞（分級器故障期間）", signals)
        # ✅ D-31（甲-5）fail-safe：分級器故障（例外或回傳無法解析）且句子非空時，
        # 不再靜默 L0——保守記 L1 供留痕（pipeline 落庫不通知）。關鍵詞命中者不受影響。
        if "llm:error" in llm.signals and text.strip() and final < RiskTier.L1:
            return RiskAssessment(RiskTier.L1, 0.0, FAILSAFE_EVENT_REASON, signals)
        return RiskAssessment(final, llm.confidence, llm.reason, signals)
