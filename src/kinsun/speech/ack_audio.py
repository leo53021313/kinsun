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

## 長輩客製化聲音（Leo 2026-08-19 需求）

家屬設了克隆聲音的長輩，過場語也要是**那個聲音**——回答是孫子的聲音、過場卻是
預設聲音，等於同一輪對話講到一半換人。故快取分「批次」存：預設聲音一批（鍵 `""`），
每個 `elder_id＋版本` 各一批，`clip_for` 依當輪解析出的 `VoiceReference` 查對應批次。

- **查無該聲音的批次＝這輪不講**（回 None，同「還沒暖好」的降級語意），並在背景
  以那個聲音整批預錄；**刻意不退回預設聲音批次**——寧可安靜，也不要在同一輪裡
  換人（需求明定過場不可以是預設或舊克隆聲音）。
- 家屬重錄＝`version` 換值＝新批次；開始預錄新批次時把同長輩的舊版本批次全數丟掉，
  舊聲音從此無從被取用。
- 回退話術（`standby_phrases`）維持預設聲音：它只在管線壞掉時出場，投遞端
  （`channels/inbound.py`）拿不到聲音解析結果，而那時聲音對不對已是次要。

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
from kinsun.speech.tts import TTSClient, TTSError, TtsPriority, VoiceReference, tts_priority

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
        standby_phrases: tuple[str, ...] = (),
    ) -> None:
        """`standby_phrases`：語庫以外、也要預錄的句子（如管線失敗的回退話術）。

        為什麼由組裝根注入而不是寫進 `speech/acks.py`：那份語庫的每一句語意都是
        「我正在查」，且有測試強制它逐工具表態。回退話術不是工具安撫話，塞進去會
        讓它被隨機抽中唸給正常對話的長輩聽。快取本身只需要知道「這些字要有音檔」。
        """
        self._tts = tts
        self._publisher = publisher
        self._ttl = signed_url_ttl_seconds
        self._clock = clock
        self._rng = rng or random.Random()
        self._standby = standby_phrases
        # 聲音鍵（"" ＝全域預設）→ 句子 → 音檔。分批的理由見檔頭「長輩客製化聲音」。
        self._entries: dict[str, dict[str, _Entry]] = {}
        self._lock = threading.Lock()
        # 正在背景預錄中的聲音鍵。同一批同時只跑一次——長輩連續發話時
        # 不該把整個語庫重複合成好幾遍。
        self._warming: set[str] = set()

    @staticmethod
    def _voice_key(voice: VoiceReference | None) -> str:
        """快取批次的鍵。版本入鍵＝家屬重錄後自然指向新批次，舊批次再也查不到。"""
        return "" if voice is None else f"{voice.elder_id}@{voice.version}"

    # ── 對話路徑（必須極快、且絕不拋例外）────────────────────────────

    def clip_for(
        self,
        tool_name: str,
        *,
        persona_id: str = acks.DEFAULT_PERSONA,
        voice: VoiceReference | None = None,
    ) -> AckClip | None:
        """這輪要唸的安撫話；還沒暖好或已過期就回 None（＝這輪不講）。

        `voice`＝這位長輩當輪的客製化聲音（無設定檔時為 None）。有克隆聲音卻還沒
        暖好時**不退回預設聲音**，理由見檔頭。

        ⚠️ 回 None 是**降級不是錯誤**：長輩退回原本的乾等體感，整輪對話照常完成。
        呼叫端不可因此讓這一輪失敗。
        """
        phrase = acks.pick(tool_name, persona_id=persona_id, rng=self._rng)
        if not phrase:
            return None
        return self.clip_for_text(phrase, voice=voice)

    def clip_for_text(self, phrase: str, voice: VoiceReference | None = None) -> AckClip | None:
        """指定這一句的音檔（不隨機抽）；還沒暖好或已過期就回 None。

        回退話術用這支（不帶 `voice`，維持預設聲音，理由見檔頭）：它是固定的一句，
        不能像工具安撫話那樣輪替。同樣**絕不當場合成**——管線已經失敗了，
        再讓長輩多等 1.9 秒沒有意義。
        """
        key = self._voice_key(voice)
        with self._lock:
            batch = self._entries.get(key)
            entry = batch.get(phrase) if batch is not None else None
            if entry is not None and self._is_stale(entry):
                # ⚠️ 過期就把**這一批**整批丟掉，不是只丟這一句：同一批的音檔是一起
                # 上傳的，簽章效期相同，一句過期就代表整批都過期了。逐句補的話，
                # 長輩會連續好幾輪都沒有安撫話（每輪隨機抽到一句沒補到的）。
                # 這是實測抓到的——`test_expired_signature_is_treated_as_missing_and_refreshed`
                # 在逐句補的版本上會紅。其他聲音的批次各有自己的上傳時刻，不陪葬。
                self._entries.pop(key, None)
                entry = None
        if entry is None:
            # 沒暖好或過期都自癒：背景整批重暖，這一輪就不講了。
            self._warm_in_background(voice)
            return None
        return AckClip(text=phrase, audio_url=entry.audio_url, duration_ms=entry.duration_ms)

    def ensure_warm(self, voice: VoiceReference | None) -> None:
        """確保這個聲音的批次存在（不存在就在背景預錄），供輪次一開始先叫。

        整批預錄要半分鐘上下；等到模型決定呼叫工具那一刻才開始暖，這位長輩第一次
        對話的過場語全都趕不上。輪次開頭（聲音解析完成時）就先叫這支，第一輪就開始
        暖，之後的對話都接得上。已暖好或正在暖都是便宜的查表，每輪呼叫無妨。
        """
        if voice is None:
            return  # 預設聲音批次由啟動時的 start_prewarm 負責
        key = self._voice_key(voice)
        with self._lock:
            batch = self._entries.get(key)
            if batch:
                return
        self._warm_in_background(voice)

    def _is_stale(self, entry: _Entry) -> bool:
        return self._clock() - entry.published_at >= self._ttl - _EXPIRY_MARGIN_SECONDS

    # ── 預熱與補寫（跑在背景，最低優先權）──────────────────────────

    @tracing.track(
        name="ack_prewarm",
        type="general",
        capture_input=False,  # 首參是 self，其餘無參數
        capture_output=False,  # 回傳 None
    )
    def prewarm(self, voice: VoiceReference | None = None) -> None:
        """把語庫裡每一句都以指定聲音合成上傳。啟動時由組裝根丟到背景執行緒（預設
        聲音）；長輩客製化聲音的批次則由 `ensure_warm`／`clip_for` 未命中時觸發。

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
        key = self._voice_key(voice)
        if voice is None:
            # 待命話術只預錄在預設聲音批次：它只在管線失敗時用得到，但**正因為那時候
            # 什麼都壞了**，它更不能依賴當場合成。去重是因為它可能剛好也在語庫裡。
            phrases = tuple(dict.fromkeys((*acks.all_phrases(), *self._standby)))
        else:
            phrases = acks.all_phrases()
            # 家屬重錄＝版本換值＝新的批次鍵。開始預錄新批次時把同長輩的**舊版本批次**
            # 全數丟掉：需求明定重錄後不可以再聽到舊克隆聲音，而舊批次的網址在簽章
            # 效期內都還播得出來，留著就是風險。
            prefix = f"{voice.elder_id}@"
            with self._lock:
                for stale_key in [k for k in self._entries if k.startswith(prefix) and k != key]:
                    del self._entries[stale_key]
        ok = sum(1 for phrase in phrases if self._publish(phrase, voice, key))
        logger.info(
            "安撫話音檔預熱完成（%s）：%d/%d 句",
            "全域預設聲音" if voice is None else f"客製化聲音 {key}",
            ok,
            len(phrases),
        )

    def _warm_in_background(self, voice: VoiceReference | None = None) -> None:
        """整批重暖。同一批同時只跑一次；不同聲音的批次彼此獨立。"""
        key = self._voice_key(voice)
        with self._lock:
            if key in self._warming:
                return
            self._warming.add(key)
        threading.Thread(
            target=self._warm_and_release,
            args=(voice,),
            name="kinsun-ack-warm",
            daemon=True,
        ).start()

    def _warm_and_release(self, voice: VoiceReference | None) -> None:
        try:
            self.prewarm(voice)
        finally:
            with self._lock:
                self._warming.discard(self._voice_key(voice))

    def _publish(self, phrase: str, voice: VoiceReference | None, key: str) -> bool:
        """以指定聲音合成並上傳一句，成功才寫進該聲音的批次。任何失敗都只留 warning。

        優先權 PREWARM：沒有任何人在等這一段，它必須讓路給長輩正在等的回覆。
        """
        try:
            with tts_priority(TtsPriority.PREWARM):
                result = self._tts.synthesize(phrase, voice=voice)
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
            self._entries.setdefault(key, {})[phrase] = _Entry(
                audio_url=url,
                duration_ms=result.duration_ms,
                published_at=self._clock(),
            )
        return True

    def warm_count(self) -> int:
        """已暖好的句數（所有聲音批次合計），供啟動檢查與測試用。"""
        with self._lock:
            return sum(len(batch) for batch in self._entries.values())


def start_prewarm(cache: AckAudioCache) -> None:
    """非阻塞地啟動預熱。

    ⚠️ 不可同步跑：十幾段 × 約 1.9 秒 ≈ 半分鐘，會把服務啟動整整擋住那麼久，
    而部署與 `--reload` 開發模式都會走到。`background.run` 在未 `configure()` 時
    是就地執行的（單元測試與 CLI 的既有語意），故這裡用裸執行緒而不是它——
    預熱是「啟動時做一次」，不是「每輪產生一筆」，不該共用那個有界佇列。
    """
    threading.Thread(target=cache.prewarm, name="kinsun-ack-prewarm", daemon=True).start()
