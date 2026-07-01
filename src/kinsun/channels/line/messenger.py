"""LINE 訊息埠：抽象出「下載語音」「回覆文字」，方便測試與替換。"""

from __future__ import annotations

from typing import Protocol


class LineMessenger(Protocol):
    def get_audio(self, message_id: str) -> bytes: ...
    def reply_text(self, reply_token: str, text: str) -> None: ...
    def push_text(self, user_id: str, text: str) -> None: ...
    def display_name(self, user_id: str) -> str: ...
    def link_rich_menu(self, user_id: str, rich_menu_id: str) -> None: ...


class LineApiMessenger:
    """正式實作：包 line-bot-sdk v3。不進 dev 單元測試（需真實憑證）。"""

    def __init__(self, access_token: str) -> None:
        from linebot.v3.messaging import (
            ApiClient,
            Configuration,
            MessagingApi,
            MessagingApiBlob,
            PushMessageRequest,
            ReplyMessageRequest,
            TextMessage,
        )

        self._configuration = Configuration(access_token=access_token)
        self._ApiClient = ApiClient
        self._MessagingApi = MessagingApi
        self._MessagingApiBlob = MessagingApiBlob
        self._PushMessageRequest = PushMessageRequest
        self._ReplyMessageRequest = ReplyMessageRequest
        self._TextMessage = TextMessage

    def get_audio(self, message_id: str) -> bytes:
        with self._ApiClient(self._configuration) as api_client:
            blob = self._MessagingApiBlob(api_client)
            return blob.get_message_content(message_id)

    def reply_text(self, reply_token: str, text: str) -> None:
        with self._ApiClient(self._configuration) as api_client:
            api = self._MessagingApi(api_client)
            api.reply_message(
                self._ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[self._TextMessage(text=text)],
                )
            )

    def push_text(self, user_id: str, text: str) -> None:
        with self._ApiClient(self._configuration) as api_client:
            api = self._MessagingApi(api_client)
            api.push_message(
                self._PushMessageRequest(
                    to=user_id,
                    messages=[self._TextMessage(text=text)],
                )
            )

    def display_name(self, user_id: str) -> str:
        try:
            with self._ApiClient(self._configuration) as api_client:
                api = self._MessagingApi(api_client)
                return api.get_profile(user_id).display_name
        except Exception:  # noqa: BLE001
            return ""

    def link_rich_menu(self, user_id: str, rich_menu_id: str) -> None:
        with self._ApiClient(self._configuration) as api_client:
            api = self._MessagingApi(api_client)
            api.link_rich_menu_id_to_user(user_id, rich_menu_id)
