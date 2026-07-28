"""安撫話音檔快取：把語庫的文字合成、上傳一次，之後每輪只是查表取網址。

## 為什麼要快取

安撫話的**全部價值就是「立刻」**。長輩問完到聽見答案有 9.5 秒（實測中位數），
先講一句「好，我幫您查一下喔」能把第一個聲音提前到 2.22 秒——但那是建立在「這句話
不必當場合成」之上：TTS 是 0.9 秒固定成本＋每字 0.10 秒，現場合成一句 10 字的安撫話
要 1.86 秒，等於把省下來的時間還掉快一半（實測：模型生成案 4.08s vs 預錄案 2.22s）。

故語庫的每一句在啟動時就合成、上傳好，對話中只是 `dict` 查表。

## 語音克隆怎麼換聲音（Leo 2026-07-28 需求二）

音檔**不進版控**，只有文字是真實來源（`speech/acks.py`）。快取只活在記憶體裡，
所以換聲音的完整流程是：**改 TTS 服務的聲音 → 重啟後端**。十幾段音檔會在背景自動
以新聲音重生，零手工步驟、零重錄、不必刪任何檔案。

⚠️ 刻意**不做**磁碟快取：那會多出「檔案裡的聲音跟現在的 TTS 不一致」這種只有重灌
才能解的狀態，而它換到的只是省下重啟後的一次背景合成——而那次合成跑在最低優先權上，
沒有任何人在等。用一個會過期的狀態換一點點 GPU 時間，不划算。

## 過期與自癒

`AudioPublisher.publish` 回的是**短效簽章 URL**（`AUDIO_SIGNED_URL_EXPIRES_SECONDS`
預設一天），不是永久網址。故每筆記下發佈時刻，接近到期就當成沒有——那一輪不講安撫話，
並在背景重新合成上傳，下一輪就好了。**絕不在對話路徑上等重新合成**：安撫話是加分項，
讓它去擋長輩的回覆是本末倒置。
"""

from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from kinsun import tracing
from kinsun.speech import acks
from kinsun.speech.tts import TTSClient, TTSError, TtsPriority, tts_priority

logger = logging.getLogger("kinsun.speech.ack_audio")

# 簽章到期前多久就視為過期。10 分鐘的餘裕足以讓背景重新合成上傳跑完，
# 而不會發生「取的時候還沒過期、長輩播的時候已經過期」。
_EXPIRY_MARGIN_SECONDS = 600.0


@dataclass(frozen=True)
class AckClip:
    """一則可以立刻送出的安撫話。"""

    text: str
    audio_url: str
    duration_ms: int


@dataclass(frozen=True)
class _Entry:
    audio_url: str
    duration_ms: int
    published_at: float


class AckAudioCache:
    """語庫文字 → 已合成上傳的音檔網址。

    `tts` 與 `publisher` 為既有的兩個 seam（`TTSClient`／`AudioPublisher`），
    故測試可以完全離線；`clock` 注入以便測到期行為。

    ⚠️ 兩個 worker 各自持有一份，各自預熱一次。刻意不做跨進程共用：重複合成十幾段
    是一次性成本，換掉一整套鎖與失效邏輯，划算。
    """

    def __init__(
        self,
        tts: TTSClient,
        publisher,
        *,
        signed_url_ttl_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        rng: random.Random | None = None,
    ) -> None:
        self._tts = tts
        self._publisher = publisher
        self._ttl = signed_url_ttl_seconds
        self._clock = clock
        self._rng = rng or random.Random()
        self._entries: dict[str, _Entry] = {}
        self._lock = threading.Lock()
        self._warming = False

    # ── 對話路徑（必須極快、且絕不拋例外）────────────────────────────

    def clip_for(
        self, tool_name: str, *, persona_name: str = acks.DEFAULT_PERSONA
    ) -> AckClip | None:
        """這輪要唸的安撫話；還沒暖好或已過期就回 None（＝這輪不講）。

        ⚠️ 回 None 是**降級不是錯誤**：長輩退回原本的乾等體感，整輪對話照常完成。
        呼叫端不可因此讓這一輪失敗。
        """
        phrase = acks.pick(tool_name, persona_name=persona_name, rng=self._rng)
        if not phrase:
            return None
        with self._lock:
            entry = self._entries.get(phrase)
            if entry is not None and self._is_stale(entry):
                # ⚠️ 過期就把**整批**丟掉，不是只丟這一句：所有音檔都在啟動時一起
                # 上傳，簽章效期相同，所以一句過期就代表全部都過期了。逐句補的話，
                # 長輩會連續好幾輪都沒有安撫話（每輪隨機抽到一句沒補到的）。
                # 這是實測抓到的——`test_expired_signature_is_treated_as_missing_and_refreshed`
                # 在逐句補的版本上會紅。
                self._entries.clear()
                entry = None
        if entry is None:
            # 沒暖好或過期都自癒：背景整批重暖，這一輪就不講了。
            self._warm_in_background()
            return None
        return AckClip(text=phrase, audio_url=entry.audio_url, duration_ms=entry.duration_ms)

    def _is_stale(self, entry: _Entry) -> bool:
        return self._clock() - entry.published_at >= self._ttl - _EXPIRY_MARGIN_SECONDS

    # ── 預熱與補寫（跑在背景，最低優先權）──────────────────────────

    @tracing.track(
        name="ack_prewarm",
        type="general",
        capture_input=False,  # 首參是 self，其餘無參數
        capture_output=False,  # 回傳 None
    )
    def prewarm(self) -> None:
        """把語庫裡每一句都合成上傳。啟動時由組裝根丟到背景執行緒。

        ⚠️ 逐句獨立處理：一句失敗不可讓其餘的都沒有音檔（TTS 服務實測會偶發 400
        與瞬斷）。失敗的那句下次被抽中時會走 `clip_for` 的自癒路徑。

        ⚠️ **這個 `@tracing.track` 不是為了觀測，是為了不污染觀測**（2026-07-28 實測）：
        `SupabaseAudioPublisher.publish` 掛著 `audio_upload` span，而預熱跑在自己的
        執行緒上、沒有父 trace——十九句就是**十九個孤兒 root trace**，而且每次 worker
        重啟、每次簽章過期重暖都會再來一輪（兩個 worker 雙倍）。實測那批孤兒把
        `care_conversation`（真正要看的東西）從列表上洗掉：探針時窗 43 筆 root trace
        裡有 26 筆是它們。掛一個 root 之後，那十九次上傳收斂成這一個 trace 底下的
        十九個 span——既看得到預熱有沒有成功，也不再洗版。
        """
        phrases = acks.all_phrases()
        ok = sum(1 for phrase in phrases if self._publish(phrase))
        logger.info("安撫話音檔預熱完成：%d/%d 句", ok, len(phrases))

    def _warm_in_background(self) -> None:
        """整批重暖。同時只跑一次——長輩連續發話時不該把整個語庫重複合成好幾遍。"""
        with self._lock:
            if self._warming:
                return
            self._warming = True
        threading.Thread(
            target=self._warm_and_release,
            name="kinsun-ack-warm",
            daemon=True,
        ).start()

    def _warm_and_release(self) -> None:
        try:
            self.prewarm()
        finally:
            with self._lock:
                self._warming = False

    def _publish(self, phrase: str) -> bool:
        """合成並上傳一句，成功才寫進快取。任何失敗都只留 warning。

        優先權 PREWARM：沒有任何人在等這一段，它必須讓路給長輩正在等的回覆。
        """
        try:
            with tts_priority(TtsPriority.PREWARM):
                result = self._tts.synthesize(phrase)
        except TTSError:
            logger.warning("安撫話合成失敗，該句暫時不可用")
            return False
        if result.audio is None:
            # 文字泡泡後端（本機開發）沒有音檔——安撫話本來就只有語音才有意義。
            return False
        try:
            url = self._publisher.publish(result.audio, content_type="audio/mp4")
        except Exception:  # noqa: BLE001 - 上傳失敗同樣只是這句暫時不可用
            logger.warning("安撫話音檔上傳失敗，該句暫時不可用")
            return False
        with self._lock:
            self._entries[phrase] = _Entry(
                audio_url=url,
                duration_ms=result.duration_ms,
                published_at=self._clock(),
            )
        return True

    def warm_count(self) -> int:
        """已暖好的句數，供啟動檢查與測試用。"""
        with self._lock:
            return len(self._entries)


def start_prewarm(cache: AckAudioCache) -> None:
    """非阻塞地啟動預熱。

    ⚠️ 不可同步跑：十幾段 × 約 1.9 秒 ≈ 半分鐘，會把服務啟動整整擋住那麼久，
    而部署與 `--reload` 開發模式都會走到。`background.run` 在未 `configure()` 時
    是就地執行的（單元測試與 CLI 的既有語意），故這裡用裸執行緒而不是它——
    預熱是「啟動時做一次」，不是「每輪產生一筆」，不該共用那個有界佇列。
    """
    threading.Thread(target=cache.prewarm, name="kinsun-ack-prewarm", daemon=True).start()
