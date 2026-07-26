"""LINE 訊息埠：抽象出「下載語音」「回覆文字」，方便測試與替換。"""

from __future__ import annotations

from typing import Protocol

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


class LineOutboundChannel:
    """OutboundChannel 的 LINE adapter：send_text 走 messenger 的 push_message。"""

    def __init__(self, messenger: LineMessenger) -> None:
        self._messenger = messenger

    def send_text(self, line_user_id: str, text: str) -> None:
        self._messenger.push_text(line_user_id, text)
