"""家屬端「長輩客製化聲音」API（2026-08-11）：權限、同意留痕、上傳、撤銷。

離線測試：`FakeVoiceProfileStore` 不碰 DB，publisher 以替身攔下上傳，
故不需要 Supabase 憑證也不需要資料庫。
"""

import threading
from datetime import datetime, timedelta, timezone
from itertools import count

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kinsun.accounts.service import AccountService
from kinsun.audio.publisher import AudioPublishError
from kinsun.schedules.service import ScheduleService
from kinsun.schedules.store import FakeScheduleStore
from kinsun.speech.tts import VoiceReference
from kinsun.voice_profiles.script import VOICE_PROFILE_SCRIPT
from kinsun.voice_profiles.store import FakeVoiceProfileStore, VoiceProfileError
from kinsun.web.auth import LineIdentity
from kinsun.web.envelope import install_error_envelope
from kinsun.web.routers import create_guardian_face_router
from tests.fakes import (
    FakeAccountStore,
    FakeConversationSummaryStore,
    FakeReminderLogStore,
    FakeRiskEventStore,
)

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 8, 11, tzinfo=TPE)
AUTH = {"Authorization": "Bearer tok"}
AUDIO = {"Content-Type": "audio/webm"}


class _FakeVerifier:
    def __init__(self, line_user_id="U-son"):
        self._line_user_id = line_user_id

    def verify(self, id_token):
        return LineIdentity(self._line_user_id, "兒子")


class _SpyPublisher:
    """記下被上傳了什麼；`boom` 時模擬 Supabase 掛掉、`sign_boom` 時模擬簽章掛掉。"""

    def __init__(self, boom=False, sign_boom=False):
        self.uploads: list[tuple[str, bytes, str]] = []
        self.deleted: list[str] = []
        self.signed: list[tuple[str, str]] = []
        self._boom = boom
        self._sign_boom = sign_boom

    def upload_voice_reference(self, elder_id, audio, *, content_type):
        if self._boom:
            raise AudioPublishError("Supabase 不通")
        self.uploads.append((elder_id, audio, content_type))
        return f"voice-refs/{elder_id}"

    def delete_voice_reference(self, elder_id):
        self.deleted.append(elder_id)

    def signed_url_for(self, path, version=""):
        if self._sign_boom:
            raise AudioPublishError("簽章不通")
        self.signed.append((path, version))
        return f"https://signed.test/{path}?v={version}"


class _SpyAckAudio:
    """記下錄後預熱被要求暖哪個聲音（2026-08-19）。"""

    def __init__(self):
        self.warmed: list[object] = []

    def ensure_warm(self, voice):
        self.warmed.append(voice)


def _accounts():
    repo = FakeAccountStore()
    ids = (f"id{i}" for i in count(1))
    svc = AccountService(repo, clock=lambda: NOW, new_id=lambda: next(ids), new_code=lambda: "c")
    svc.create_elder("U-son", "兒子", "阿公")
    return svc


def _client(accounts, *, profiles=None, publisher=None, verifier=None, ack_audio=None):
    app = FastAPI()
    install_error_envelope(app)
    app.include_router(
        create_guardian_face_router(
            verifier=verifier or _FakeVerifier(),
            accounts=accounts,
            schedules=ScheduleService(FakeScheduleStore(), clock=lambda: NOW),
            clock=lambda: NOW,
            risk_events=FakeRiskEventStore(),
            reminder_logs=FakeReminderLogStore(),
            summaries=FakeConversationSummaryStore(),
            appointment_hour=8,
            voice_profiles=profiles,
            publisher=publisher,
            ack_audio=ack_audio,
        ),
        prefix="/api/v1",
    )
    return TestClient(app)


def _elder_id(accounts):
    return accounts.elders_managed_by("U-son")[0].elder_id


@pytest.fixture()
def setup():
    accounts = _accounts()
    profiles, publisher = FakeVoiceProfileStore(), _SpyPublisher()
    client = _client(accounts, profiles=profiles, publisher=publisher)
    return client, _elder_id(accounts), profiles, publisher


# --- 朗讀稿 ---


def test_script_is_served_by_the_server_not_hardcoded_in_the_frontend(setup):
    """稿子與逐字稿必須是同一份文字，分兩邊維護遲早會漂移，故由伺服器下發。"""
    client, *_ = setup
    body = client.get("/api/v1/voice-profile-script", headers=AUTH).json()["data"]

    assert body["script"] == VOICE_PROFILE_SCRIPT
    assert body["tips"], "要附錄音注意事項給家屬看"


def test_the_script_satisfies_the_recording_guidelines():
    """稿子是把錄製準則「內建」的手段，改稿不可以破壞它們。

    各項皆有 DGX 實機實測支撐，理由見 voice_profiles/script.py 的
    SCRIPT_RATIONALE 與 services/tts/README.md 的「參考語音的錄製準則」。
    """
    text = VOICE_PROFILE_SCRIPT
    # 2026-08-19 滲漏實測：稿子的字會被機率性唸進回覆（40 字舊稿 2/4～3/4 次），
    # 故①稿長必須壓在官方參考樣本的量級（15 字）②不可含稱謂——滲漏出來就是叫錯人。
    plain = text.replace("，", "").replace("。", "")
    assert 12 <= len(plain) <= 22, (
        f"逐字稿過長會滲進回覆（舊稿 40 字實測 3/4），實際 {len(plain)} 字"
    )
    assert "嬤" not in text and "阿公" not in text, "稱謂滲漏＝對著阿公喊阿嬤，不可入稿"
    assert text.count("喔") >= 2, "「喔」要句中與句尾各一次，兩種型態都要學到"
    # 句中至少一次＝「喔」後面還有下文，不是整段的結尾。
    assert any(
        text[i + 1] not in "。" for i, c in enumerate(text) if c == "喔" and i + 1 < len(text)
    ), "「喔」至少要有一次出現在句中"


# --- 權限 ---


def test_a_guardian_cannot_touch_an_elder_they_do_not_manage(setup):
    """越權一律 404（不洩漏該長輩是否存在），與其他長輩資源同一慣例。"""
    client, _elder, _profiles, _pub = setup
    for method, kwargs in (
        ("get", {}),
        (
            "put",
            {"params": {"consented_by": "孫子"}, "headers": {**AUTH, **AUDIO}, "content": b"x"},
        ),
        ("delete", {}),
    ):
        res = getattr(client, method)(
            "/api/v1/elders/not-mine/voice-profile", **{"headers": AUTH, **kwargs}
        )
        assert res.status_code == 404, method


def test_requests_without_a_token_are_rejected(setup):
    client, elder_id, *_ = setup
    assert client.get(f"/api/v1/elders/{elder_id}/voice-profile").status_code == 401


# --- 建立 ---


def test_uploading_sets_the_profile_with_the_system_script_as_transcript(setup):
    """逐字稿直接取系統下發的稿子——家屬照唸，所以不必猜也不必辨識。"""
    client, elder_id, profiles, publisher = setup

    res = client.put(
        f"/api/v1/elders/{elder_id}/voice-profile",
        params={"consented_by": "孫子小明本人於通話中同意"},
        headers={**AUTH, **AUDIO},
        content=b"RECORDING",
    )

    assert res.status_code == 200
    saved = profiles.get_active(elder_id)
    assert saved.prompt_text == VOICE_PROFILE_SCRIPT
    assert saved.prompt_audio_path == f"voice-refs/{elder_id}"
    assert saved.consented_by == "孫子小明本人於通話中同意"
    assert saved.granted_at == NOW.timestamp()
    assert publisher.uploads == [(elder_id, b"RECORDING", "audio/webm")]


def test_consent_is_required(setup):
    """這是**別人的聲音**，要被拿去對長輩說話——沒有人明確同意就不該建立。

    與 D-13 的 consents 表同一把尺。
    """
    client, elder_id, profiles, publisher = setup

    res = client.put(
        f"/api/v1/elders/{elder_id}/voice-profile",
        params={"consented_by": "   "},  # 只有空白＝沒填
        headers={**AUTH, **AUDIO},
        content=b"RECORDING",
    )

    assert res.status_code == 400
    assert res.json()["error"]["code"] == "consent_required"
    assert profiles.get_active(elder_id) is None, "沒同意就不該留下設定檔"
    assert publisher.uploads == [], "更不該把聲音上傳出去"


def test_non_audio_body_is_rejected(setup):
    client, elder_id, _profiles, publisher = setup

    res = client.put(
        f"/api/v1/elders/{elder_id}/voice-profile",
        params={"consented_by": "孫子"},
        headers={**AUTH, "Content-Type": "application/json"},
        content=b'{"oops": 1}',
    )

    assert res.status_code == 415
    assert publisher.uploads == []


def test_empty_recording_is_rejected(setup):
    client, elder_id, *_ = setup
    res = client.put(
        f"/api/v1/elders/{elder_id}/voice-profile",
        params={"consented_by": "孫子"},
        headers={**AUTH, **AUDIO},
        content=b"",
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "missing_audio"


def test_upload_failure_does_not_leave_a_profile_pointing_at_nothing():
    """上傳失敗不寫設定檔。

    寫了就會指向一個不存在的物件，之後每一輪都要走一次「下載失敗→退回全域預設」，
    而家屬那端以為已經設定好了——那是最難查的一種失效。
    """
    accounts = _accounts()
    profiles = FakeVoiceProfileStore()
    client = _client(accounts, profiles=profiles, publisher=_SpyPublisher(boom=True))
    elder_id = _elder_id(accounts)

    res = client.put(
        f"/api/v1/elders/{elder_id}/voice-profile",
        params={"consented_by": "孫子"},
        headers={**AUTH, **AUDIO},
        content=b"RECORDING",
    )

    assert res.status_code == 502
    assert profiles.get_active(elder_id) is None


def test_store_failure_does_not_report_success():
    """音檔上傳成功但設定檔寫不進去：要誠實回報失敗，不能回 200。"""

    class _BoomStore(FakeVoiceProfileStore):
        def save(self, profile):
            raise VoiceProfileError("db down")

    accounts = _accounts()
    client = _client(accounts, profiles=_BoomStore(), publisher=_SpyPublisher())

    res = client.put(
        f"/api/v1/elders/{_elder_id(accounts)}/voice-profile",
        params={"consented_by": "孫子"},
        headers={**AUTH, **AUDIO},
        content=b"RECORDING",
    )

    assert res.status_code == 503


# --- 查看與撤銷 ---


def test_status_does_not_expose_the_voice_sample(setup):
    """查詢設定狀態不需要能把聲音拿走：不回音檔、也不回可下載的網址。"""
    client, elder_id, *_ = setup
    client.put(
        f"/api/v1/elders/{elder_id}/voice-profile",
        params={"consented_by": "孫子"},
        headers={**AUTH, **AUDIO},
        content=b"RECORDING",
    )

    body = client.get(f"/api/v1/elders/{elder_id}/voice-profile", headers=AUTH).json()["data"]

    assert body["has_profile"] is True
    assert body["consented_by"] == "孫子"
    assert "prompt_audio_path" not in body
    assert not any("http" in str(v) for v in body.values())


def test_status_before_any_upload(setup):
    client, elder_id, *_ = setup
    body = client.get(f"/api/v1/elders/{elder_id}/voice-profile", headers=AUTH).json()["data"]
    assert body["has_profile"] is False


def test_revoking_falls_back_to_the_global_voice(setup):
    """撤銷後 get_active 回 None，管線據此退回全域預設聲音。"""
    client, elder_id, profiles, _pub = setup
    client.put(
        f"/api/v1/elders/{elder_id}/voice-profile",
        params={"consented_by": "孫子"},
        headers={**AUTH, **AUDIO},
        content=b"RECORDING",
    )

    res = client.delete(f"/api/v1/elders/{elder_id}/voice-profile", headers=AUTH)

    assert res.status_code == 204
    assert profiles.get_active(elder_id) is None


def test_revoking_also_deletes_the_stored_recording(setup):
    """撤銷要連 bucket 裡的聲音樣本一起刪掉（2026-08-12）。

    只標記停用的話，那段錄音會永遠留在 bucket——`cleanup(retention_days)` 只掃
    `tts/` 底下的日期資料夾，`voice-refs/` 不在它的範圍內。這是長輩家人的聲紋，
    家屬按下撤銷的意思是「不要再留著」，不是「先藏起來」。
    """
    client, elder_id, _profiles, publisher = setup
    client.put(
        f"/api/v1/elders/{elder_id}/voice-profile",
        params={"consented_by": "孫子"},
        headers={**AUTH, **AUDIO},
        content=b"RECORDING",
    )

    client.delete(f"/api/v1/elders/{elder_id}/voice-profile", headers=AUTH)

    assert publisher.deleted == [elder_id]


def test_endpoints_return_503_when_the_feature_is_not_enabled():
    """TTS 非 dgx 或缺 Supabase 時：端點仍在但回 503。

    ⚠️ 刻意不讓整支 router 消失——404 會讓前端誤以為自己打錯路徑，
    503 才講得出「這個環境沒開這個功能」。
    """
    accounts = _accounts()
    client = _client(accounts, profiles=None, publisher=None)
    elder_id = _elder_id(accounts)

    assert client.get(f"/api/v1/elders/{elder_id}/voice-profile", headers=AUTH).status_code == 503


# --- 錄後預熱（Leo 2026-08-19 需求追加）---


def _join_prewarm_threads():
    for thread in threading.enumerate():
        if thread.name == "kinsun-ack-warm-on-set":
            thread.join(timeout=5)


def test_setting_a_profile_prewarms_the_ack_batch_with_the_new_voice():
    """家屬錄完的當下就用新聲音預錄安撫話，不等長輩第一次開口。

    整批預錄要半分鐘——等長輩開口才開始的話，第一場對話的過場語全趕不上；
    錄完就開暖，家屬把手機拿給長輩之前多半已經好了。
    """
    accounts = _accounts()
    profiles, publisher = FakeVoiceProfileStore(), _SpyPublisher()
    ack = _SpyAckAudio()
    client = _client(accounts, profiles=profiles, publisher=publisher, ack_audio=ack)
    elder_id = _elder_id(accounts)

    res = client.put(
        f"/api/v1/elders/{elder_id}/voice-profile",
        params={"consented_by": "孫子小明本人於通話中同意"},
        headers={**AUTH, **AUDIO},
        content=b"RECORDING",
    )

    assert res.status_code == 200
    _join_prewarm_threads()
    version = str(NOW.timestamp())
    assert publisher.signed == [(f"voice-refs/{elder_id}", version)], (
        "簽章必須帶新版本——重錄後其他快取層靠它換新"
    )
    assert ack.warmed == [
        VoiceReference(
            elder_id=elder_id,
            prompt_audio_url=f"https://signed.test/voice-refs/{elder_id}?v={version}",
            prompt_text=VOICE_PROFILE_SCRIPT,
            version=version,
        )
    ]


def test_prewarm_signing_failure_does_not_fail_the_upload():
    """預熱是加分項：簽章掛掉只記 warning，設定本身照樣成功（200）。"""
    accounts = _accounts()
    profiles = FakeVoiceProfileStore()
    publisher = _SpyPublisher(sign_boom=True)
    ack = _SpyAckAudio()
    client = _client(accounts, profiles=profiles, publisher=publisher, ack_audio=ack)
    elder_id = _elder_id(accounts)

    res = client.put(
        f"/api/v1/elders/{elder_id}/voice-profile",
        params={"consented_by": "孫子小明本人於通話中同意"},
        headers={**AUTH, **AUDIO},
        content=b"RECORDING",
    )

    assert res.status_code == 200
    _join_prewarm_threads()
    assert ack.warmed == [], "簽不出網址就不該硬暖——長輩開口時 ensure_warm 會再試"
    assert profiles.get_active(elder_id) is not None, "設定檔必須已寫入"


def test_no_prewarm_when_ack_audio_is_not_wired():
    """未注入 ack_audio（既有呼叫端）：PUT 行為與過去完全相同，不簽章、不預熱。"""
    accounts = _accounts()
    profiles, publisher = FakeVoiceProfileStore(), _SpyPublisher()
    client = _client(accounts, profiles=profiles, publisher=publisher)
    elder_id = _elder_id(accounts)

    res = client.put(
        f"/api/v1/elders/{elder_id}/voice-profile",
        params={"consented_by": "孫子小明本人於通話中同意"},
        headers={**AUTH, **AUDIO},
        content=b"RECORDING",
    )

    assert res.status_code == 200
    _join_prewarm_threads()
    assert publisher.signed == []
