"""LINE 訊息埠：抽象出「下載語音」「回覆文字」，方便測試與替換。"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Protocol

from tenacity import (
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    stop_after_delay,
    wait_exponential,
)

from kinsun.notifications.models import NotificationSeverity

logger = logging.getLogger("kinsun.channels.line")

# 出站重試（2026-07-27）：次數與總時長雙上限。
# 總時長上限的存在理由：危急通報排在長輩的回覆生成**之前**（pipeline.py），而連線逾時
# 每次要花滿 LINE_API_TIMEOUT_SECONDS——只設次數，最壞情況會讓長輩多等三十秒。
#
# ⚠️ **`LINE_SEND_MAX_TOTAL_SECONDS` 不是硬上限**（2026-07-27 更正，原註解寫錯）：
# tenacity 的 `stop_after_delay` 只在兩次嘗試**之間**判定，不會中斷已經在跑的那一次
# （其 docstring 逐字寫「max_delay will be exceeded」）。實際最壞是
# `10s（第一次吃滿逾時）＋0.5s（退避）＋10s（第二次吃滿）≈ 20.5 秒`。
# 要真正的硬上限得換 `stop_before_delay`，但那會在退避前就放棄、等於少試一次，
# 對「確定沒送出去」的危急通知不划算，故維持現狀並在此據實載明。
#
# ⚠️ 另一個必須知道的放大效應：這個上限是**每位家屬、每個通道各一份**。
# `GuardianNotifier.notify` 是序列迴圈（safety/notifier.py），而它排在長輩的回覆之前——
# 三位家屬同時失敗時，長輩最壞要多等約 60 秒。真正的解法是把家屬通報移出長輩的
# 回覆路徑（`background.run`），那是架構層變更，需另案評估。
LINE_SEND_MAX_ATTEMPTS = 3
LINE_SEND_MAX_TOTAL_SECONDS = 15.0
LINE_SEND_BACKOFF_SECONDS = 0.5

# LINE API 的每次呼叫逾時（秒）。與 LIFF 驗證、音檔上傳同級（皆 10 秒）——都是短往返的
# HTTP，慢到十秒就是對方出事了，繼續等只是把長輩一起拖下水。
#
# ⚠️ 為什麼非有不可（2026-07-27）：先前**一個呼叫都沒有設**，LINE 一旦假死，該輪對話
# 永遠不返回，佔住一個 uvicorn worker 與一條 Postgres 連線（池上限只有 5）；而家屬危急
# 通報排在回覆生成之前（pipeline.py），卡住的代價是長輩連回覆都拿不到。本專案為完全
# 同型的問題付過兩次學費：llm.py 的 Gemini 逾時存進欄位卻從沒傳給 SDK、db.py 的死 TCP
# 讓排程器停擺七小時。
#
# 不開成環境變數：目前沒有人需要調，且 config.py 已 502 行。真的要調的那天再升格。
LINE_API_TIMEOUT_SECONDS = 10.0


class LineMessenger(Protocol):
    def get_audio(self, message_id: str) -> bytes: ...
    def reply_text(self, reply_token: str, text: str) -> None: ...
    def push_text(self, line_user_id: str, text: str) -> None: ...
    def display_name(self, line_user_id: str) -> str: ...
    def link_rich_menu(self, line_user_id: str, rich_menu_id: str) -> None: ...
    def reply_voice(
        self, reply_token: str, audio_url: str, duration_ms: int, text: str | None
    ) -> None: ...


class LineApiMessenger:
    """正式實作：包 line-bot-sdk v3。不進 dev 單元測試（需真實憑證）。

    ⚠️ **新增任何對外呼叫時，一律要傳 `_request_timeout=self._timeout`。** SDK 的
    `Configuration` 沒有全域逾時設定（只吃 host／憑證／CA），只能逐次傳，因此漏傳不會
    有任何徵兆——直到某次 LINE 假死才發現。`test_every_line_api_call_carries_a_timeout`
    逐一列出所有出口守住這件事，新方法請一併加進那份清單。
    """

    def __init__(self, access_token: str, *, timeout: float = LINE_API_TIMEOUT_SECONDS) -> None:
        from linebot.v3.messaging import (
            ApiClient,
            AudioMessage,
            Configuration,
            MessagingApi,
            MessagingApiBlob,
            PushMessageRequest,
            ReplyMessageRequest,
            TextMessage,
        )

        self._configuration = Configuration(access_token=access_token)
        # ⚠️ 關掉 urllib3 的隱形重試（2026-07-27 黑洞位址實測）：`_request_timeout` 是
        # **每次嘗試**的上限，不是總時限。預設 `retries=None` 讓 urllib3 自己重試 3 次，
        # 實測逾時設 2 秒、實際 8 秒才放棄——上面那個「10 秒」的承諾會悄悄變成 40 秒，
        # 而且整個過程一行日誌都沒有。
        # 重試不是不要，是要放在看得見的地方：危急通知的補送在 channels 層自己做，
        # 有退避、有日誌、且明確排除逾時（可能已送達，重試會讓家屬收到兩則相同的警報）。
        self._configuration.retries = 0
        self._timeout = timeout
        self._ApiClient = ApiClient
        self._AudioMessage = AudioMessage
        self._MessagingApi = MessagingApi
        self._MessagingApiBlob = MessagingApiBlob
        self._PushMessageRequest = PushMessageRequest
        self._ReplyMessageRequest = ReplyMessageRequest
        self._TextMessage = TextMessage

    def get_audio(self, message_id: str) -> bytes:
        with self._ApiClient(self._configuration) as api_client:
            blob = self._MessagingApiBlob(api_client)
            return blob.get_message_content(message_id, _request_timeout=self._timeout)

    def reply_text(self, reply_token: str, text: str) -> None:
        with self._ApiClient(self._configuration) as api_client:
            api = self._MessagingApi(api_client)
            api.reply_message(
                self._ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[self._TextMessage(text=text)],
                ),
                _request_timeout=self._timeout,
            )

    def push_text(self, line_user_id: str, text: str) -> None:
        with self._ApiClient(self._configuration) as api_client:
            api = self._MessagingApi(api_client)
            api.push_message(
                self._PushMessageRequest(
                    to=line_user_id,
                    messages=[self._TextMessage(text=text)],
                ),
                _request_timeout=self._timeout,
            )

    def display_name(self, line_user_id: str) -> str:
        try:
            with self._ApiClient(self._configuration) as api_client:
                api = self._MessagingApi(api_client)
                return api.get_profile(line_user_id, _request_timeout=self._timeout).display_name
        except Exception:  # noqa: BLE001
            return ""

    def link_rich_menu(self, line_user_id: str, rich_menu_id: str) -> None:
        with self._ApiClient(self._configuration) as api_client:
            api = self._MessagingApi(api_client)
            api.link_rich_menu_id_to_user(
                line_user_id, rich_menu_id, _request_timeout=self._timeout
            )

    def reply_voice(
        self, reply_token: str, audio_url: str, duration_ms: int, text: str | None
    ) -> None:
        messages = [self._AudioMessage(original_content_url=audio_url, duration=duration_ms)]
        if text is not None:
            messages.append(self._TextMessage(text=text))
        with self._ApiClient(self._configuration) as api_client:
            api = self._MessagingApi(api_client)
            api.reply_message(
                self._ReplyMessageRequest(reply_token=reply_token, messages=messages),
                _request_timeout=self._timeout,
            )


def _is_retryable_send_error(exc: BaseException) -> bool:
    """這次失敗「確定沒送出去」嗎？只有確定的才重試。

    分類依 2026-07-27 實測（本機假伺服器＋黑洞位址，`retries=0` 下）：
    - `MaxRetryError`：連線根本沒建立（拒絕連線、連線逾時、DNS）→ 請求沒送出去，**可重試**。
    - `ServiceException`（5xx）：LINE 自己沒處理成功 → **可重試**。
    - `ReadTimeoutError`：連線建立了、請求送出去了，只是沒等到回應 → 那則通知**可能已經
      送達**，重試會讓家屬收到兩則一模一樣的危急警報。**不重試**。
    - 4xx（Unauthorized／Forbidden／NotFound／ApiException）：請求本身有問題（token 失效、
      被封鎖），重送幾次都一樣，只是拖慢通報。**不重試**。

    ⚠️ 白名單而非黑名單：認不出來的例外一律不重試。這裡的預設值必須偏向「少送一次」，
    因為多送一次的代價是家屬對危急警報失去信任。
    """
    from linebot.v3.messaging.exceptions import ServiceException
    from urllib3.exceptions import MaxRetryError

    return isinstance(exc, MaxRetryError | ServiceException)


class LineOutboundChannel:
    """OutboundChannel 的 LINE adapter：send_text 走 messenger 的 push_message。

    帶有界重試：`ChannelRouter` 這一層原本零重試，一次網路抖動就等於一則危急通知永久
    消失（只留一行連時間戳都沒有的 log）。urllib3 自己那套隱形重試已經關掉（見
    `LineApiMessenger`），所以重試改在這裡做——看得見、有日誌、而且挑得了對象。
    """

    def __init__(
        self, messenger: LineMessenger, *, sleep: Callable[[float], None] | None = None
    ) -> None:
        self._messenger = messenger
        # 注入點供測試斷言退避而不真的睡（沿用 rag/embeddings.py 的既有寫法）。
        self._sleep = sleep if sleep is not None else time.sleep

    def send_text(
        self,
        line_user_id: str,
        text: str,
        *,
        severity: NotificationSeverity = NotificationSeverity.NOTICE,
    ) -> None:
        """送出並在「確定沒送出去」時重試；重試用盡仍把例外往上拋。

        ⚠️ **`severity` 在 LINE 這條路上刻意不做任何事**（2026-08-01）：LINE 的
        push message 是純文字，收訊端的通知樣式由 LINE App 決定，我們給不了
        「紅色」或「打斷式宣告」。參數存在只是為了滿足 `OutboundChannel` 這個
        共用 Protocol——`ChannelRouter` 對每個通道都用同一組引數呼叫，少了它
        LINE 綁定的長輩會在送出時直接炸 TypeError。**不要**改成把等級字樣塞進
        文案：文案由 `safety/notifier.py::_format_alert` 統一產生，2026-07-29
        Leo 已定案不放家屬看不懂的「風險等級」字樣。

        ⚠️ 例外必須往上拋、不可吞掉：`ChannelRouter` 靠它把這個通道記成投遞失敗，
        吞掉會讓「送出去了」與「三次都失敗」在留痕上長得一模一樣。

        ⚠️ 總時長必須有界：危急通報排在長輩的回覆生成**之前**（`pipeline.py`），
        這裡多等一秒，長輩就晚一秒聽到回應。故除了次數上限，另加一道總時長上限——
        連線逾時每次要花滿 `LINE_API_TIMEOUT_SECONDS`，只靠次數擋不住最壞情況。
        """
        attempt = 0

        def _send() -> None:
            nonlocal attempt
            attempt += 1
            if attempt > 1:
                logger.warning("LINE 出站重試第 %d 次 principal=%s", attempt - 1, line_user_id)
            self._messenger.push_text(line_user_id, text)

        Retrying(
            stop=(
                stop_after_attempt(LINE_SEND_MAX_ATTEMPTS)
                | stop_after_delay(LINE_SEND_MAX_TOTAL_SECONDS)
            ),
            wait=wait_exponential(multiplier=LINE_SEND_BACKOFF_SECONDS, exp_base=2, max=2.0),
            retry=retry_if_exception(_is_retryable_send_error),
            sleep=self._sleep,
            reraise=True,
        )(_send)
