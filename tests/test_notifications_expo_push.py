"""Expo Push 客戶端：ticket 解析與死 token 辨識。

為什麼要測這些：推播失敗全部是靜默的——長輩不會知道、家屬不會知道、伺服器
只留一行 warning。唯一會被發現的症狀是「提醒好像沒響」，而那時候已經很難查。
"""

from __future__ import annotations

import json

import pytest

from kinsun.notifications.expo_push import ExpoPushClient, PushError


class _FakeResponse:
    def __init__(self, payload: dict, status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self._payload


class _FakeHttp:
    """記下送出的訊息並回指定的 ticket 陣列。"""

    def __init__(self, tickets_per_call: list[list[dict]] | None = None, status: int = 200) -> None:
        self.calls: list[list[dict]] = []
        self._tickets = tickets_per_call or [[{"status": "ok"}]]
        self._status = status

    def post(self, url: str, content: str, headers: dict) -> _FakeResponse:
        self.calls.append(json.loads(content))
        tickets = self._tickets[min(len(self.calls) - 1, len(self._tickets) - 1)]
        return _FakeResponse({"data": tickets}, self._status)


def _client(http: _FakeHttp, **kwargs) -> ExpoPushClient:
    return ExpoPushClient(client=http, **kwargs)


def test_no_tokens_does_not_call_expo():
    http = _FakeHttp()

    outcome = _client(http).send([], "提醒", "該吃藥了")

    assert http.calls == []
    assert outcome.sent == 0


def test_sends_title_and_body_to_each_token():
    http = _FakeHttp([[{"status": "ok"}, {"status": "ok"}]])

    outcome = _client(http).send(["tokA", "tokB"], "金孫提醒您", "早上該吃血壓藥囉")

    assert outcome.sent == 2
    assert outcome.failed == 0
    sent = http.calls[0]
    assert [m["to"] for m in sent] == ["tokA", "tokB"]
    assert sent[0]["title"] == "金孫提醒您"
    assert sent[0]["body"] == "早上該吃血壓藥囉"


def test_device_not_registered_is_reported_as_dead_token():
    """裝置永久收不到了：呼叫端要據此清掉，否則每次派送都白打一次。"""
    http = _FakeHttp(
        [[{"status": "ok"}, {"status": "error", "details": {"error": "DeviceNotRegistered"}}]]
    )

    outcome = _client(http).send(["good", "dead"], "提醒", "內容")

    assert outcome.sent == 1
    assert outcome.failed == 1
    assert outcome.dead_tokens == ("dead",)


def test_transient_error_is_not_treated_as_dead():
    """速率超限是暫時的——把它當死 token 清掉會讓那台裝置從此收不到提醒。"""
    http = _FakeHttp([[{"status": "error", "details": {"error": "MessageRateExceeded"}}]])

    outcome = _client(http).send(["tok"], "提醒", "內容")

    assert outcome.failed == 1
    assert outcome.dead_tokens == ()


def test_error_without_details_does_not_crash():
    http = _FakeHttp([[{"status": "error", "message": "something went wrong"}]])

    outcome = _client(http).send(["tok"], "提醒", "內容")

    assert outcome.failed == 1
    assert outcome.dead_tokens == ()


def test_batches_over_100_tokens():
    """Expo 單次上限 100 則；101 台裝置要分兩次送，不可整批被拒。"""
    http = _FakeHttp([[{"status": "ok"}] * 100, [{"status": "ok"}]])

    outcome = _client(http).send([f"tok{i}" for i in range(101)], "提醒", "內容")

    assert len(http.calls) == 2
    assert len(http.calls[0]) == 100
    assert len(http.calls[1]) == 1
    assert outcome.sent == 101


def test_access_token_goes_into_authorization_header():
    class _Capturing(_FakeHttp):
        headers: dict = {}

        def post(self, url: str, content: str, headers: dict):
            _Capturing.headers = headers
            return super().post(url, content, headers)

    http = _Capturing()
    _client(http, access_token="secret-token").send(["tok"], "提醒", "內容")

    assert _Capturing.headers["Authorization"] == "Bearer secret-token"


def test_no_access_token_sends_no_authorization_header():
    class _Capturing(_FakeHttp):
        headers: dict = {}

        def post(self, url: str, content: str, headers: dict):
            _Capturing.headers = headers
            return super().post(url, content, headers)

    http = _Capturing()
    _client(http).send(["tok"], "提醒", "內容")

    assert "Authorization" not in _Capturing.headers


def test_http_error_raises_push_error():
    http = _FakeHttp(status=500)

    with pytest.raises(PushError):
        _client(http).send(["tok"], "提醒", "內容")


def test_unexpected_payload_raises_push_error():
    class _Bad(_FakeHttp):
        def post(self, url: str, content: str, headers: dict) -> _FakeResponse:
            return _FakeResponse({"errors": ["nope"]})

    with pytest.raises(PushError):
        _client(_Bad()).send(["tok"], "提醒", "內容")
