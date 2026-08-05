"""App 對講機的 WebSocket 通道：整輪對話走同一條長連線（spec 2026-07-28 P2）。

## 為什麼整輪都走它，而不是只加一條下行通道

非同步回覆要讓後端**主動**送第二則訊息（先「稍等我喔」、答案好了再送）。後端正式模式
跑兩個 worker（`WEB_WORKERS` 預設 2），連線由作業系統分派——若錄音照舊走
`POST /turns`、只另外加一條下行 WebSocket，長輩的連線可能握在 worker A、他的錄音卻
落在 worker B，**算出答案的那個推不出去**。整輪同一條連線讓歸屬問題自動消失，
不必新增任何基礎設施（Redis／LISTEN NOTIFY），也不必退回單 worker。

額外紅利：同一位長輩的所有併發輪必然在同一條連線、同一個 worker 底下，P3 的
「在途清單」可以直接掛在連線物件上。

## 協定

上行：
- 一個 **binary** 訊息 ＝ 一輪完整音檔（不做串流錄音——ASR 目前是整檔 API，
  改串流是獨立工程）。
- 一個 **JSON** 訊息可先送位置：`{"location": "…", "latitude": …, "longitude": …}`。
  它只更新「下一輪要用的位置」，不自成一輪。

下行（皆帶 `turn_id`）：
- `ack`——模型決定要查東西時。欄位：`text`、`audio_url`、`duration_ms`
- `queued`——容量閘門滿載時排隊告知位置（spec 2026-07-30 §10 B2，P3 Task 2）。
  欄位：`position`（**排隊名次**，1-based；`admission.py::admit` 的
  `position = len(self._queue)`。⚠️ **不是「前面還有幾位」**——`limit=1` 時
  兩者剛好相等，但正式環境 `limit=TURN_CONCURRENCY_LIMIT`（預設 6）時，
  排隊名次 1 的人前面其實還有 6 輪正在跑，只是不在佇列裡）。
- `reply`——答案算完但**沒有音檔**（TTS 失敗退純文字）。欄位：`text`、`audio_url`（空）、
  `duration_ms`、`chunk_count`、`reply_digest`
- `error`——任一段失敗，或排隊逾時／每分鐘輪數保險絲觸發。欄位：`text`（回退話術，
  三種情形共用同一句 `_BUSY_REPLY`）
- **binary frame**——答案算完且有音檔（2026-07-30 延遲優化 C1）。格式：
  `[4 bytes 大端序 header 長度][UTF-8 JSON header][m4a bytes]`，header 欄位與 `reply`
  完全相同（`type` 亦為 `"reply"`）。
- **binary frame（type="chunk"）**——續段語音（2026-08-01）。header 欄位：
  `turn_id`、`index`（從 1 起）、`text`、`duration_ms`、`is_last`。
  ⚠️ `turn_id` 是必要的：併發之下同時可能有多輪在推段，前端靠它歸屬。
  ⚠️ `index` 有一個例外：續段合成中途失敗（或本來就切不出第二段）時，會補送一個
  `index=0、text=""、audio` 為空、`is_last=true` 的終止訊框——`index` 因此**不保證 ≥1**。
  `index=0` 不是續段編號，是「這輪講完了（不論是不是講完整）」的哨兵值（見
  `_push_continuation_chunks`）。
  ⚠️ **`is_last` 目前沒有任何客戶端在讀**（2026-08-01 全分支審查 Important 2 核實：
  `web/src/` 全庫只有型別宣告與測試 fixture）。它是**協定欄位**，不是前端的結束條件
  ——網頁端回到待機是由**播放佇列排空**驅動的（`useTalk.ts` 的 drain 完成後轉
  `idle`），這條路不需要知道「還有沒有下一段」。終止訊框仍然照送：它讓**未來的**
  客戶端（或別的通道）有辦法知道這一輪講完了，而這種「送得出去卻沒人讀」的欄位
  一旦停送就再也補不回來。**不要**改成讓前端去消費 `is_last`——那會把「回到待機」
  這件事變成兩個來源說了算，兩者不同調時長輩會卡在「說話中」。

⚠️ **為什麼 header 要嵌在 binary frame 裡，而不是「先送 JSON 再送 binary」**：同一條
連線最多三輪併發（`_MAX_CONCURRENT_TURNS`），兩輪幾乎同時算完時，「JSON(A)、JSON(B)、
binary(A)、binary(B)」的交錯是完全可能的——App 就會把 A 的音檔配上 B 的字幕。把 header
放進同一個 frame 讓每個 frame 自我描述，交錯就不再是問題，也不需要任何關聯狀態。

⚠️ 為什麼值得做（2026-07-30 十輪實測）：原本的路是「後端上傳 Supabase→取簽章 URL→
App 拿到 URL→App 再向 Supabase 下載」，音檔在網路上走兩趟，長輩要等完第一趟（實測
0.54 秒，尖峰 2.37 秒）才**開始**下載第二趟。改成 bytes 直送後，上傳降級為存證、
排在推送之後（見 `VoiceReplyDelivery._deliver_inline`）。

`POST /turns` 保留不動：LINE 通道仍走 `dispatch`，且 WebSocket 連不上時必須有降級路徑。

## 兩個非做不可的實作要點

⚠️ **收到音檔立刻交給執行緒池**，不可在讀迴圈裡跑完整輪。底下整段（ASR、Gemini、
TTS、落庫）全是同步阻塞呼叫，留在讀迴圈裡等於長輩在等答案時的第二次發話根本讀不進來
——P3 的併發對話會直接失效。這與 `turns.py` 的 `run_in_threadpool` 是同一個教訓。

⚠️ **從工作執行緒送訊息要跨回事件迴圈**：`WebSocket.send_json` 是 async 的，而安撫話
與回覆都是在工作執行緒裡產生的。故以 `asyncio.run_coroutine_threadsafe` 交還給迴圈，
並在送出失敗時只留 warning——連線斷了不該讓那一輪的落庫與記憶寫入跟著炸掉。
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from kinsun import tracing
from kinsun.accounts.models import Channel, PrincipalType
from kinsun.accounts.service import AccountService
from kinsun.agent import SYSTEM_TROUBLE_REPLY
from kinsun.channels.app.admission import AdmissionTimeout, TurnAdmission
from kinsun.channels.app.inbound_audio import start_inbound_upload
from kinsun.channels.inbound import InboundMessage, dispatch
from kinsun.locations.store import ElderLocation, is_valid_coordinate, is_valid_place
from kinsun.speech.chunking import split_for_speech
from kinsun.speech.tts import TTSError, TtsPriority, tts_priority
from kinsun.turn_context import (
    pending_utterances,
    tool_announcer,
    transcript_listener,
    turn_directive,
)

logger = logging.getLogger("kinsun.channels.app.ws")

_DEFAULT_MAX_AUDIO_BYTES = 10 * 1024 * 1024

# 關閉碼。1008＝policy violation，用於認證與同意複核失敗。
_CLOSE_UNAUTHORIZED = 1008

# 同時在跑的輪數上限（spec 2026-07-28 P3）。
#
# 長輩連按麥克風會開出無限多輪，每一輪都佔一條執行緒、一組 Gemini 呼叫與一次 TTS。
# 無上限的代價與 `background.py` 的佇列上限同源：撐爆行程比少回一句嚴重得多。
# 3 是「連問三件事還撐得住」與「不失控」之間的取捨——實測長輩的自然節奏是一次一件，
# 併發兩輪已經是少見情形。
_MAX_CONCURRENT_TURNS = 3
_BUSY_REPLY = "金孫還在忙前面那幾句，等一下下再跟您說好嗎？"

# 容量閘門（spec 2026-07-30 §10 B2）未被注入 `TurnAdmission` 時的備援併發上限
# ——正式環境一律由 `app.py` 注入 `Settings.turn_concurrency_limit`，這裡只是
# 讓沒有特別關心閘門的呼叫端（大多數既有測試）維持「幾乎不會排隊」的舊行為。
_DEFAULT_TURN_CONCURRENCY = 6

# 晚到答案的回指指示。⚠️ 走系統提示而不是程式層硬前綴——拼接出來的句子 TTS 唸起來
# 會斷裂，而這句話要讓長輩覺得是金孫自己想起來的。
_LATE_REPLY_DIRECTIVE = (
    "（系統提示）長輩問完這句之後又講了別的，所以這個答案是慢了幾句才回來的。"
    "開頭請自然帶一句回指，讓他知道你在回哪一個問題"
    "（例如「對了，您剛剛問的那個喔」），不要突兀地直接講答案。"
)


class _NullBinding:
    """App 無文字選單流程：handle 一律回 None（與 `turns.py` 相同）。"""

    def handle(self, external_id: str, text: str) -> None:
        return None


class _TurnCollector:
    """收集 dispatch 的回覆：文字與（若有）公開音檔 URL（與 `turns.py` 相同）。

    C1 之後多一條路：`reply_audio` 直接把音檔 frame 推出去（不經 `audio_url`），
    並登記 `audio_sent`——`_run_turn` 據此不再補送 JSON `reply`，否則長輩會收到兩份
    同一輪的回覆（音檔一份、文字一份），播放佇列會把同一句話唸兩次。

    ⚠️ `self.text` 是**投遞層的顯示字串**（要放進訊框給長輩看的那一份），不是真正的
    回覆文字：`ASR_DEBUG_SHOW_TRANSCRIPT=true` 時 `inbound.py::_compose_text` 會回
    「辨識：…\\n\\n回復：…」。任何「拿回覆文字再做一次處理」的用途（例如續段切句）
    一律要用 `DeliveryOutcome.reply_text`，不可用這個欄位——2026-08-01 審查
    Critical 1 就是把它餵進 `split_for_speech` 造成的。
    """

    def __init__(self, sender: _Sender | None = None, turn_id: str = "") -> None:
        self.text = ""
        self.audio_url = ""
        self.duration_ms: int | None = None
        self.audio_sent = False
        self._sender = sender
        self._turn_id = turn_id

    def reply(self, text: str) -> None:
        self.text = text

    def reply_voice(self, audio_url: str, duration_ms: int, text: str | None) -> None:
        self.audio_url = audio_url
        self.duration_ms = duration_ms
        if text:
            self.text = text

    def reply_audio(
        self,
        audio: bytes,
        duration_ms: int,
        text: str | None,
        chunk_count: int,
        reply_digest: str,
    ) -> None:
        """把音檔本體隨 binary frame 直接推給 App（C1）。例外原樣往外拋（見 `_Sender`）。"""
        self.duration_ms = duration_ms
        if text:
            self.text = text
        header = {
            "type": "reply",
            "turn_id": self._turn_id,
            "text": self.text,
            "audio_url": "",  # 音檔就在同一個 frame 裡，App 不必再下載
            "duration_ms": duration_ms,
            "chunk_count": chunk_count,
            "reply_digest": reply_digest,
        }
        self._sender.send_reply_audio(header, audio)
        self.audio_sent = True


class _InFlight:
    """這條連線上還在跑的輪（spec 2026-07-28 P3）。

    ⚠️ 掛在**連線**上而不是全域：整輪走同一條 WebSocket，所以同一位長輩的所有併發輪
    必然在同一條連線、同一個 worker 底下——這正是「整輪走 WebSocket」換來的紅利，
    不需要任何跨進程機制。

    只存在記憶體、被濫用審核攔下的輪直接丟棄，故不違反「被攔的輪不進記憶」的安全契約。
    """

    def __init__(self) -> None:
        self._turns: dict[str, str] = {}  # turn_id → 長輩的原話（ASR 之後才有）
        self._order: list[str] = []  # 依開口順序，用來判斷誰是最新的一輪
        self._lock = threading.Lock()

    def start(self, turn_id: str) -> bool:
        """登記一輪；超過上限回 False（呼叫端據此回一句「還在忙」）。"""
        with self._lock:
            if len(self._order) >= _MAX_CONCURRENT_TURNS:
                return False
            self._turns[turn_id] = ""
            self._order.append(turn_id)
            return True

    def set_utterance(self, turn_id: str, text: str) -> None:
        with self._lock:
            if turn_id in self._turns:
                self._turns[turn_id] = text

    def finish(self, turn_id: str) -> None:
        with self._lock:
            self._turns.pop(turn_id, None)
            if turn_id in self._order:
                self._order.remove(turn_id)

    def others(self, turn_id: str) -> list[str]:
        """其他還在跑的輪，長輩講過的話（依開口順序，排除自己與尚未辨識完的）。"""
        with self._lock:
            return [
                self._turns[other]
                for other in self._order
                if other != turn_id and self._turns.get(other)
            ]

    def is_latest(self, turn_id: str) -> bool:
        """這一輪是不是長輩最後講的那一句——不是就代表答案晚到了，回覆要帶回指。"""
        with self._lock:
            return not self._order or self._order[-1] == turn_id


def encode_reply_frame(header: dict, audio: bytes) -> bytes:
    """把 header 與音檔打包成自我描述的 binary frame（見模組 docstring 的協定說明）。

    4 bytes 大端序長度前綴而非分隔符：JSON 裡可以出現任何位元組序列，用分隔符掃描
    遲早會被長輩講的某句話炸掉。
    """
    raw = json.dumps(header, ensure_ascii=False).encode("utf-8")
    return len(raw).to_bytes(4, "big") + raw + audio


class _Sender:
    """從工作執行緒把訊息送回 WebSocket。

    ⚠️ 送出失敗只留 warning、不往外拋：連線在對話進行中斷掉是常態（長輩走出訊號範圍、
    App 被切到背景），而那一輪的落庫與記憶寫入不該跟著炸掉。
    """

    def __init__(self, websocket: WebSocket, loop: asyncio.AbstractEventLoop) -> None:
        self._websocket = websocket
        self._loop = loop

    def send(self, payload: dict, *, timeout: float = 5.0) -> None:
        """送出一則下行訊框；`timeout` 決定呼叫端最長願意等多久（見 `notify_queued`
        為什麼要傳短一點的原因）。"""
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._websocket.send_json(payload), self._loop
            )
            future.result(timeout=timeout)
        except Exception:  # noqa: BLE001 - 連線斷掉不可中斷那一輪的其餘工作
            logger.warning("WebSocket 送出失敗 type=%s", payload.get("type"))

    def send_reply_audio(self, header: dict, audio: bytes) -> None:
        """送出內嵌音檔的回覆 frame（C1）。

        ⚠️ 失敗必須**往外拋**（與 `send` 相反）：呼叫端是
        `VoiceReplyDelivery._deliver_inline`，它接到例外才會退回文字泡泡——吞掉的話
        長輩這一輪就什麼都收不到，而回覆絕不可消失。
        """
        future = asyncio.run_coroutine_threadsafe(
            self._websocket.send_bytes(encode_reply_frame(header, audio)), self._loop
        )
        future.result(timeout=5)

    def send_chunk_audio(self, header: dict, audio: bytes) -> None:
        """送出續段音檔訊框（2026-08-01）。

        ⚠️ 失敗只記 warning、**不往外拋**（與 `send_reply_audio` 相反）：第一段推不出去
        代表長輩這一輪什麼都收不到，必須讓投遞層退回文字泡泡；續段推不出去時他已經
        聽到開頭了，為此把整輪打回文字反而更糟。
        """
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._websocket.send_bytes(encode_reply_frame(header, audio)), self._loop
            )
            future.result(timeout=5)
        except Exception:  # noqa: BLE001 - 續段送不出去不可中斷那一輪的其餘工作
            logger.warning("續段音檔送出失敗 index=%s", header.get("index"))


def create_app_ws_router(
    *,
    accounts: AccountService,
    pipeline,
    gate,
    voice,
    traces=None,
    inbound_audio=None,
    ack_audio=None,
    tts=None,
    locations=None,
    new_id: Callable[[], str] | None = None,
    clock: Callable[[], datetime] | None = None,
    max_audio_bytes: int = _DEFAULT_MAX_AUDIO_BYTES,
    admission: TurnAdmission | None = None,
    rate_limiter=None,
) -> APIRouter:
    router = APIRouter(tags=["turns"])
    make_id = new_id or (lambda: uuid.uuid4().hex)
    now = clock or (lambda: datetime.now(UTC))
    # ⚠️ 刻意不叫 `gate`：本函式的 `gate` 參數是 `ConsentGate`（同意複核），命名
    # 相撞會讓 `dispatch(gate=gate, ...)` 悄悄改傳錯物件。一定要在這裡（工廠層級）
    # 建立一次並讓所有輪次共用——放進 `_run_turn` 內部會讓每一輪各自算一個新的
    # `TurnAdmission`，閘門就永遠不會真的擋到人。
    turn_gate = admission or TurnAdmission(_DEFAULT_TURN_CONCURRENCY)

    def _resolve_elder(token: str) -> tuple[str, str] | None:
        """token → (elder_id, external_id)；認證或同意複核失敗回 None。

        與 `turns.py` 的 `current_elder` ＋ 同意複核等價——**閘門不可省**：
        token 不代表同意，撤回或綁定消失即擋。
        """
        auth = accounts.authenticate_token(token) if token else None
        if auth is None or auth.principal_type is not PrincipalType.ELDER:
            return None
        external_id = accounts.app_external_id_of_elder(auth.principal_id)
        if external_id is None or gate.resolve_elder(Channel.APP, external_id) is None:
            return None
        return auth.principal_id, external_id

    def _save_location(elder_id: str, place: str, lat, lon) -> None:
        """記下長輩回報的地點（與 `turns.py` 的 `_save_location` 同一套規則）。

        三者必須同時具備才寫入；空地名＝「這輪沒有位置」，不寫入也不清空既有資料。
        """
        # 地名太長＝這輪沒有位置（V-05，2026-07-29）：判準與 REST 共用，見 locations/store。
        if locations is None or not is_valid_place(place) or lat is None or lon is None:
            return
        place = place.strip()
        try:
            locations.save(
                ElderLocation(elder_id, place, now().timestamp(), float(lat), float(lon))
            )
        except Exception:  # noqa: BLE001 - 位置是加分項，寫入失敗不可中斷對話
            logger.warning("長輩地點寫入失敗")

    def _ack_sender(sender: _Sender, turn_id: str) -> Callable[[list[str]], None]:
        """做出「模型決定要查什麼」時要跑的那件事：挑一句安撫話立刻送出去。

        ⚠️ 這裡**不合成、不上傳**——音檔在啟動時就備好了（見 `speech/ack_audio.py`）。
        現場合成一句 10 字的安撫話要 1.86 秒，等於把這個功能省下來的延遲還掉快一半。
        """

        def announce(tool_names: list[str], persona_id: str) -> None:
            if ack_audio is None:
                return
            # 人設由 agent 隨通知帶過來（2026-08-05），這裡**不查資料庫**：那一輪
            # 的長輩檔案 agent 已經讀過了，為一句等待語再查一次是白付一次往返。
            clip = ack_audio.clip_for(tool_names[0], persona_id=persona_id)
            if clip is None:  # 還沒暖好或簽章過期＝這輪不講（降級不是錯誤）
                return
            sender.send(
                {
                    "type": "ack",
                    "turn_id": turn_id,
                    "text": clip.text,
                    "audio_url": clip.audio_url,
                    "duration_ms": clip.duration_ms,
                }
            )

        return announce

    # ⚠️ **這個 span 目前是 Opik 上的孤兒 root trace，不是掛在對話那棵樹底下**
    # （2026-08-01 全分支審查 Important 3，已在本機 Opik 實測確認）：本函式的呼叫點
    # 在 `dispatch(...)` **回傳之後**，那時 `care_conversation`（trace root）與
    # `care_turn_voice` 都已關閉、opik 的 context 已清空，而
    # `opik/decorator/span_creation_handler.py::create_span_respecting_context` 在
    # 「沒有 current span 也沒有 current trace」時會**新建一棵 trace**。實測（本機
    # Opik，獨立專案）：一輪跑完後後端存在兩筆 root trace——`care_conversation` 與
    # `tts_chunks`。因此每一輪都會多產生一棵孤兒樹（舊的 REST 續拉是每次續拉一棵）。
    # 要修得把續段納入對話那棵樹的生命週期（例如以 distributed trace headers 承接，
    # 或把續段搬進 `care_turn_voice` 之內），那是結構性改動，不在這一波範圍；此處
    # 只誠實記載，設計文件 §5.5 原本宣稱「順帶修掉孤兒 root trace」已同步更正。
    # ⚠️ **不要為了修它而搬動呼叫點**：這個位置同時承載 D-2（續段留在
    # `turn_gate.admit()` 之內）與 Important 1（在途清單在續段之前解除）兩項約束。
    @tracing.track(
        name="tts_chunks",
        type="general",
        capture_input=False,  # reply_text 已在 care_turn_voice 的 I/O 裡
        capture_output=False,  # 回傳 None
    )
    def _push_continuation_chunks(sender: _Sender, reply_text: str, turn_id: str) -> None:
        """把第一段之後的句子逐段合成並推出去（spec 2026-08-01）。

        `reply_text` 必須是**真正的回覆文字**（`DeliveryOutcome.reply_text`／
        `TtsResult.text`），不可是投遞層的顯示字串——理由與 `speech/chunking.py::
        reply_digest` 的警告同一個，見呼叫點的說明。

        ⚠️ 自己呼叫 `split_for_speech` 而不是從 `TtsResult` 拿：它是純函式，同樣輸入
        必得同樣輸出；改 `TtsResult` 協定會波及所有測試替身，換不到任何東西。已隨
        2026-08-01 續段語音 WS 直送移除的 REST 續拉端點（`turns.py::get_turn_chunk`）
        原本也是這樣做的。

        優先權 `CHUNK`：長輩正在聽第一段、續段有餘裕，別位長輩的第一段（`REPLY`）
        應該先做。
        """
        sent_terminator = False
        # ⚠️ 整段包一層 try（2026-08-01 全分支審查）：底下只接得住 `TTSError`，而
        # TTS client 換人（或 `split_for_speech` 有 bug）時冒出來的別種例外會一路
        # 衝到 `_run_turn` 的 `except Exception`，於是長輩明明已經聽到第一段，畫面
        # 卻跳出系統錯誤訊息並提前回到待機。機率低，但這是改動前不存在的失敗形態
        # ——續段炸掉最多就是「後半段沒講」，不該把已經成功的前半段一起打成錯誤。
        try:
            # `tts` 未注入＝這個 router 組不出續段（正式環境恆有，見 `app.py`）。
            # ⚠️ 刻意不在這裡 `return`：終止訊框是協定層的承諾（見模組 docstring 的
            # 下行協定），不該因為某種組裝方式少注入一個依賴就默默不送——同一個函式
            # 底下才剛寫著「無論如何都要有終止訊號」。
            chunks = split_for_speech(reply_text) if tts is not None else []
            for index, text in enumerate(chunks[1:], start=1):
                is_last = index == len(chunks) - 1
                try:
                    with tts_priority(TtsPriority.CHUNK):
                        result = tts.synthesize(text)
                except TTSError:
                    logger.warning("續段合成失敗 turn=%s index=%s", turn_id, index)
                    break
                if result.audio is None:
                    logger.warning("續段無音檔 turn=%s index=%s", turn_id, index)
                    break
                sender.send_chunk_audio(
                    {
                        "type": "chunk",
                        "turn_id": turn_id,
                        "index": index,
                        "text": text,
                        "duration_ms": result.duration_ms,
                        "is_last": is_last,
                    },
                    result.audio,
                )
                logger.info("續段推出 turn=%s index=%s 字數=%s", turn_id, index, len(text))
                sent_terminator = is_last
        except Exception:  # noqa: BLE001 - 續段炸掉不可把已經送出的前半段打成錯誤
            logger.exception("續段推送意外失敗 turn=%s", turn_id)
        if not sent_terminator:
            # ⚠️ 無論如何都要有終止訊號：協定承諾每一輪都以 `is_last=true` 收尾，
            # 缺了會讓「讀 `is_last` 的客戶端」把該輪當成還沒結束。中途失敗（合成
            # 炸掉或無音檔）與「切不出第二段」（迴圈根本沒跑）都會走到這裡，補送一個
            # 空音檔、空文字的終止訊框。
            # ⚠️ 現況核實（2026-08-01 審查 Important 2）：**目前的網頁客戶端不讀
            # `is_last`**，它回到待機是靠播放佇列排空。所以這個訊框此刻沒有消費者，
            # 送它是為了守住協定、留給未來的客戶端——但也正因為沒人讀，它的
            # `text: ""` 曾經在前端把字幕整個抹掉（同日審查 Critical 2）：空音檔
            # 讓它不進播放佇列，卻擋不住它走過字幕那條路。前端已補上空字串守門。
            sender.send_chunk_audio(
                {
                    "type": "chunk",
                    "turn_id": turn_id,
                    "index": 0,
                    "text": "",
                    "duration_ms": 0,
                    "is_last": True,
                },
                b"",
            )

    def _run_turn(
        *,
        sender: _Sender,
        in_flight: _InFlight,
        audio: bytes,
        elder_id: str,
        external_id: str,
        turn_id: str,
        received_at: float,
    ) -> None:
        """一輪對話的同步本體（在工作執行緒裡跑）。

        流程與 `turns.py::_run_turn` 一致，差別只在：回覆用 `sender` 推出去而不是
        當成 HTTP 回應，且中途多一則安撫話。

        ⚠️ 容量閘門（spec §10 B2）包住的是 `dispatch(...)`（真正打 ASR／TTS 的那一
        段），而不是這裡的上傳與物件組裝——閘門要擋的是「同時打到 GPU 的輪數」，
        排在它之前的都不吃 GPU，提早佔位只會讓排隊位置變得不誠實。
        """
        # 背景上傳，不等網址：見 `channels/app/inbound_audio.py`（延遲優化 B1）。
        start_inbound_upload(inbound_audio, traces, audio, turn_id)
        collector = _TurnCollector(sender, turn_id)
        msg = InboundMessage(
            Channel.APP,
            external_id,
            "audio",
            "",
            audio,
            collector.reply,
            collector.reply_voice,
            trace_id=turn_id,
            audio_url="",
            received_at=received_at,
            # 音檔本體直接走這條連線回去（C1）：投遞層據此走內嵌路徑、跳過
            # 「上傳→簽章→App 再下載」兩趟網路。
            reply_audio=collector.reply_audio,
        )
        # 晚到回指（spec P3）：長輩在這一輪還沒回來之前又講了別的，答案回去時
        # 要讓他知道在回哪一個問題。判斷點在**開跑前**——那時已經知道自己是不是
        # 最新的一輪，而系統提示必須在 LLM 呼叫之前就備好。
        directive = "" if in_flight.is_latest(turn_id) else _LATE_REPLY_DIRECTIVE

        def notify_queued(position: int) -> None:
            # ⚠️ 短逾時（1 秒，而非 `send` 預設的 5 秒）：`admission.py::admit`
            # docstring 講的還輕——這個回呼雖然在閘門**沒有持鎖**時被呼叫，但
            # 呼叫當下這個號碼已經**在佇列裡**（取號在鎖內完成、佇列非空才走到
            # 這裡），故快速通道的「佇列是空的」這個前提在此刻對所有人都不成立：
            # 任何人在這段時間嘗試 `admit()`（不管有沒有空位）都會被逼進佇列、
            # 等這通回呼結束才恢復正常——一支訊號不良的手機（送出被 TCP 背壓卡住）
            # 可讓**全域**入場停擺，GPU 閒置、`active()` 顯示滿載，卻沒有人在
            # 做事，正是這個閘門要避免的畫面。壓到 1 秒把曝險窗縮到原本的五分之一；
            # `queued` 本身是禮貌訊框（送丟了長輩仍會在逾時或答案好時收到
            # error／reply，不會真的音訊全無），值得用較短的逾時換全域入場的
            # 反應性。
            sender.send({"type": "queued", "turn_id": turn_id, "position": position}, timeout=1.0)

        try:
            try:
                with turn_gate.admit(on_queued=notify_queued):
                    with (
                        tool_announcer(_ack_sender(sender, turn_id)),
                        transcript_listener(lambda text: in_flight.set_utterance(turn_id, text)),
                        pending_utterances(lambda: in_flight.others(turn_id)),
                        turn_directive(directive),
                    ):
                        outcome = dispatch(
                            msg,
                            pipeline=pipeline,
                            binding=_NullBinding(),
                            gate=gate,
                            voice=voice,
                            traces=traces,
                            elder_id=elder_id,  # 入口已解析並複核同意（✅ 庚-12）
                        )
                    # ⚠️ **在途登記在這裡解除，不等續段跑完**（2026-08-01 全分支審查
                    # Important 1）：走到這裡代表答案已經送到長輩耳朵、且本輪記憶已寫進
                    # `turns` 表（`pipeline._settle_memory_write` 盡力而為 0.5 秒上限、逾時記
                    # warning 放行——永不阻擋回覆送出；但若背景寫入落後超過 0.5 秒且長輩在那
                    # 窗口內插嘴，A 的問句會同時缺席 `shortterm.recent()` 與在途清單），
                    # 這一輪對「還在處理中」的定義而言已經結束。續段迴圈還要跑 7～10 秒，若把
                    # 解除留給下面的 finally，長輩這段期間插嘴問 B 時，B 的情境會同時
                    # 看到 A 的問句（`shortterm.recent()` 已含 A 的問答配對）與
                    # `current_pending_utterances()` 再附一次 A 的問句——模型看到
                    # `user:A / assistant:A答 / user:A / user:B`，一個**已經回答過的
                    # 問題**被當成還沒回答擺在最新位置。`turn_context.pending_utterances`
                    # 的定義是「還有哪些話**正在處理中**」，答案已入耳的不該還在裡面。
                    # ⚠️ 這裡解除的只是**在途清單**的名額；容量閘門的名額仍照 D-2 保留
                    # 到續段跑完（續段一樣打 GPU）——兩者是不同的東西，不可一起搬。
                    # ⚠️ 下面的 finally 仍留著同一行：`finish` 是冪等的（`pop` 預設值
                    # ＋`in` 判斷），而失敗與排隊逾時那兩條路徑走不到這裡。
                    in_flight.finish(turn_id)
                    if collector.audio_sent:
                        # 續段直送（2026-08-01）：第一段已經在播了，剩下的逐段合成、逐段推出去。
                        # ⚠️ 迴圈在 `turn_gate.admit()` 的 with 區塊**之內**（見上方 try 的縮排）：
                        # 續段一樣打 GPU，閘門要擋的就是這個。放外面會讓 `active()` 低估實際負載。
                        # ⚠️ 餵的是 `outcome.reply_text`（**真正的回覆文字**），不是
                        # `collector.text`（投遞層的顯示字串，見 `_TurnCollector.text`）：
                        # `ASR_DEBUG_SHOW_TRANSCRIPT=true` 時後者是「辨識：…\n\n回復：…」，
                        # 切出來的段落與 `pipeline._synthesize` 切的不是同一組，長輩會先聽到
                        # 第一句、再聽到「回復：」加同一句重播（2026-08-01 審查 Critical 1）。
                        # `outcome` 為 None 理論上到不了這裡（`audio_sent` 為真代表投遞層跑完
                        # 且 `_run_pipeline` 回了 outcome）；真的發生就只送終止訊框，寧可少講
                        # 後半段，也不要拿一串不知道是什麼的文字去合成。
                        _push_continuation_chunks(
                            sender, outcome.reply_text if outcome else "", turn_id
                        )
                        return
            except AdmissionTimeout:
                logger.warning("排隊逾時，婉拒這一輪 elder=%s turn=%s", elder_id, turn_id)
                sender.send({"type": "error", "turn_id": turn_id, "text": _BUSY_REPLY})
                return
            except Exception:  # noqa: BLE001 - 一輪失敗不可打斷整條連線
                logger.exception("WebSocket 對話輪失敗 turn=%s", turn_id)
                sender.send({"type": "error", "turn_id": turn_id, "text": SYSTEM_TROUBLE_REPLY})
                return
        finally:
            # ⚠️ 一定要在 finally：這一輪失敗或排隊逾時時若沒有解除登記，`in_flight`
            # 的名額會一直被佔著，長輩問滿三次之後就再也得不到回應。閘門本身的名額
            # 由 `turn_gate.admit()` 自己的 finally 釋放，不必在這裡重複處理。
            # ⚠️ 成功那條路徑已經在續段之前先解除過一次（見上方說明），這裡是重複但
            # 無害的保險——`_InFlight.finish` 冪等。刪掉它會讓失敗與逾時兩條路徑漏掉
            # 解除，那正是本行最初存在的理由。
            in_flight.finish(turn_id)
        # ⚠️ 走到這裡代表 `collector.audio_sent` 必為 False：音檔 frame（與續段）已在
        # `with turn_gate.admit()` 之內就近推送並 return，不會落到這裡；此處只剩
        # 純文字回覆（TTS 失敗退純文字）需要補送 JSON reply。
        chunk_count = outcome.chunk_count if outcome else 0
        sender.send(
            {
                "type": "reply",
                "turn_id": turn_id,
                "text": collector.text,
                "audio_url": collector.audio_url,
                "duration_ms": collector.duration_ms,
                "chunk_count": chunk_count,
                "reply_digest": outcome.reply_digest if outcome else "",
            }
        )

    @router.websocket("/ws/talk")
    async def talk(websocket: WebSocket) -> None:
        # token 走 query string：WebSocket 握手在瀏覽器與 React Native 都不能自訂
        # Authorization 標頭（`expo` 的 WebSocket 亦然），這是該協定的普遍作法。
        # ⚠️ 因此 token 會進入伺服器的存取日誌——`logging_setup` 不記 query string，
        # 但反向代理可能會，部署時須留意。
        token = websocket.query_params.get("token", "")
        resolved = _resolve_elder(token)
        if resolved is None:
            await websocket.close(code=_CLOSE_UNAUTHORIZED)
            return
        elder_id, external_id = resolved
        await websocket.accept()
        loop = asyncio.get_running_loop()
        sender = _Sender(websocket, loop)
        in_flight = _InFlight()
        pending: dict = {}  # 下一輪要用的位置（由 JSON 訊息帶入）
        try:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    return
                text = message.get("text")
                if text is not None:
                    pending = _parse_location(text)
                    continue
                audio = message.get("bytes")
                if not audio:
                    continue
                received_at = time.monotonic()
                if len(audio) > max_audio_bytes:
                    sender.send({"type": "error", "turn_id": "", "text": SYSTEM_TROUBLE_REPLY})
                    continue
                # ⚠️ 位置必須排在這一輪之前：長輩這句話問的就是天氣時，這一輪就得用到。
                _save_location(
                    elder_id,
                    pending.get("location", ""),
                    pending.get("latitude"),
                    pending.get("longitude"),
                )
                turn_id = make_id()
                # 每位長輩的保險絲（spec §10 B2）：純粹防前端 bug（重連迴圈狂送），
                # 對真人操作等同無限，走到這裡幾乎一定是程式在打自己。排在 `in_flight`
                # 之前——被擋下的這一輪不該去佔用途中清單的名額。
                if rate_limiter is not None and not rate_limiter.hit(f"turn:{elder_id}"):
                    logger.warning("長輩輪數超過每分鐘上限 elder=%s", elder_id)
                    sender.send({"type": "error", "turn_id": turn_id, "text": _BUSY_REPLY})
                    continue
                if not in_flight.start(turn_id):
                    # 連按太多次：回一句「還在忙」而不是靜默丟掉，長輩才知道發生什麼事。
                    logger.warning("併發輪達上限，婉拒這一輪 elder=%s", elder_id)
                    sender.send({"type": "error", "turn_id": turn_id, "text": _BUSY_REPLY})
                    continue
                # ⚠️ 一定要丟執行緒池：整輪是同步阻塞的，留在讀迴圈裡就讀不到
                # 長輩等待期間的第二次發話——P3 的併發對話會直接失效。
                # 不 await：這正是「等待中還能繼續講話」的實作方式。
                loop.run_in_executor(
                    None,
                    lambda a=audio, t=turn_id, r=received_at: _run_turn(
                        sender=sender,
                        in_flight=in_flight,
                        audio=a,
                        elder_id=elder_id,
                        external_id=external_id,
                        turn_id=t,
                        received_at=r,
                    ),
                )
        except WebSocketDisconnect:
            return

    return router


def _parse_location(raw: str) -> dict:
    """解析上行的位置 JSON；壞掉就當成「這輪沒有位置」。

    外部輸入是資料不是指令：解析失敗只丟掉這一筆，不可讓一則畸形訊息切斷長輩的連線。

    ⚠️ 型別必須在這裡擋（V-03，2026-07-29）：`_save_location` 的 `place.strip()`
    在它自己的 try 之外，地名傳成數字會拋 AttributeError 一路冒到讀迴圈——那裡只接
    `WebSocketDisconnect`，於是**整條連線被砍、且不送任何 error 訊框**。
    最陰險的是發作時機：位置訊框只是存進 `pending`，要等長輩**下一次開口**送音檔
    才會用到，所以症狀是「講完一整句話，連線斷掉，那句話也沒進庫」。只要 App 某個
    版本把 `location` 送成數字，該版本**所有使用者**的第一句話都會斷線。
    REST 那條路因 FastAPI 強制轉字串不受影響，只有 WS 這條主路徑中招。

    三者型別任一不合就整筆丟掉，不接受半套——反正 `_save_location` 本來就要求
    三者齊備，留半筆只是讓「這輪沒有位置」多一種說法。
    """
    import json

    try:
        payload = json.loads(raw)
    except ValueError:
        logger.warning("WebSocket 位置訊息不是合法 JSON，忽略")
        return {}
    if not isinstance(payload, dict):
        return {}
    location = payload.get("location", "")
    latitude = payload.get("latitude")
    longitude = payload.get("longitude")
    # ⚠️ 「沒帶座標」要與「帶了但不合法」分開：前者是既有的正常語意（只送地名＝這輪
    # 沒有位置），把它也記成 warning 等於製造誤導性日誌——那正是讓下一個人查錯方向
    # 的東西。
    if latitude is None and longitude is None:
        return {}
    if not isinstance(location, str) or not is_valid_coordinate(latitude, longitude):
        logger.warning("WebSocket 位置訊框欄位不合法（型別或範圍），整筆忽略")
        return {}
    return {"location": location, "latitude": latitude, "longitude": longitude}
