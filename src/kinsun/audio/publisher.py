"""音檔發佈：把音檔上傳 Supabase Storage 私有 bucket，回短效簽章 URL（✅ D-55）。

標準庫 urllib（不加 supabase SDK）；service key 走環境變數。
路徑帶日期資料夾 {prefix}/{yyyymmdd}/（prefix 預設 tts，進站音檔用 inbound）。
簽章效期由 AUDIO_SIGNED_URL_EXPIRES_SECONDS 控制；檔案本體預設不清理
（AUDIO_RETENTION_DAYS=0，2026-07-09 修訂），設 >0 才啟用過期資料夾清理。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Protocol

from kinsun import tracing
from kinsun.transport import HttpxTransport, Transport, TransportError, read_json

logger = logging.getLogger("kinsun.audio")

# 長輩客製化聲音參考音檔的簽章網址效期與快取（2026-08-01）。
# 一小時足夠涵蓋一輪對話與 DGX 端的下載，又短到就算外流也很快失效；
# 提前 5 分鐘換發，避免把「剩沒幾秒」的網址交給 DGX 而在下載途中過期。
_VOICE_URL_TTL_SECONDS = 3600
_VOICE_URL_REFRESH_MARGIN_SECONDS = 300


class AudioPublishError(Exception):
    """音檔上傳／清理失敗。"""


class AudioPublisher(Protocol):
    def publish(self, audio: bytes, *, content_type: str) -> str: ...


class SupabaseAudioPublisher:
    def __init__(
        self,
        base_url: str,
        service_key: str,
        bucket: str,
        *,
        timeout: float,
        clock: Callable[[], datetime],
        new_id: Callable[[], str],
        prefix: str = "tts",
        transport: Transport | None = None,
        signed_url_expires_seconds: int = 86400,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._key = service_key
        self._bucket = bucket
        self._timeout = timeout
        self._clock = clock
        self._new_id = new_id
        self._prefix = prefix.strip("/")
        self._transport = transport or HttpxTransport()
        self._signed_url_expires_seconds = signed_url_expires_seconds
        # 物件路徑 → (簽章網址, 這份快取的失效時刻)。見 signed_url_for 的說明。
        self._voice_url_cache: dict[str, tuple[str, datetime]] = {}

    def _object_path(self, name: str) -> str:
        return f"{self._prefix}/{self._clock().strftime('%Y%m%d')}/{name}"

    @tracing.track(
        name="audio_upload",
        type="general",
        capture_input=True,
        capture_output=True,
        ignore_arguments=["audio"],  # 整包音檔 bytes
    )
    def publish(self, audio: bytes, *, content_type: str) -> str:
        path = self._object_path(f"{self._new_id()}.m4a")
        upload_url = f"{self._base}/storage/v1/object/{self._bucket}/{path}"
        try:
            self._transport.request(
                "POST",
                upload_url,
                data=audio,
                headers={"Authorization": f"Bearer {self._key}", "Content-Type": content_type},
                timeout=self._timeout,
            )
        except TransportError as exc:
            raise AudioPublishError(f"音檔上傳失敗：{exc}") from exc
        return self._create_signed_url(path)

    def upload_voice_reference(self, elder_id: str, audio: bytes, *, content_type: str) -> str:
        """上傳某位長輩的客製化參考音檔，回傳 bucket 內的**物件路徑**（不是網址）。

        與 `publish` 的三個刻意差異：
        - **路徑固定為 `voice-refs/<elder_id>`**，不帶日期或亂數。一位長輩只有一組
          生效聲音（`voice_profiles` 的 PK 就是 elder_id），重錄即覆蓋；散落成多份
          只會讓「哪一份才是生效的」變成要對照資料庫才知道的事。
        - **回路徑而非網址**：`voice_profiles.prompt_audio_path` 存路徑，用時才由
          `signed_url_for` 現簽短效網址（存死的簽章網址會過期，見該方法說明）。
        - **不受 `cleanup(retention_days)` 影響**：那支只掃 `tts/` 底下的日期資料夾，
          參考音檔放在 `voice-refs/` 不會被當成過期的回覆音檔掃掉。

        ⚠️ 覆蓋既有物件需要 `x-upsert`，Supabase 預設會對已存在的路徑回 400。
        """
        path = f"voice-refs/{elder_id}"
        upload_url = f"{self._base}/storage/v1/object/{self._bucket}/{path}"
        try:
            self._transport.request(
                "POST",
                upload_url,
                data=audio,
                headers={
                    "Authorization": f"Bearer {self._key}",
                    "Content-Type": content_type,
                    "x-upsert": "true",
                },
                timeout=self._timeout,
            )
        except TransportError as exc:
            raise AudioPublishError(f"參考音檔上傳失敗：{exc}") from exc
        # 覆蓋後舊網址仍指向同一路徑但內容已換，行程內快取會發出舊簽章直到到期——
        # 對 DGX 端而言那是同一個 URL、可能命中它自己的快取而拿到舊聲音。直接失效。
        self._voice_url_cache.pop(path, None)
        return path

    def delete_voice_reference(self, elder_id: str) -> None:
        """刪掉某位長輩的參考音檔（家屬撤銷客製化聲音時，2026-08-12）。

        ⚠️ **失敗不拋**：撤銷是否生效的權威是 `voice_profiles.revoked_at` 那一次資料庫
        寫入，不是這次網路呼叫。反過來設計（刪不掉就讓撤銷失敗）會讓家屬收到錯誤、
        以為沒撤銷成功，但聲音其實已經停用了——那比留一個孤兒物件更糟。刪不掉的檔案
        不會再被任何人讀到（`resolve_voice` 只看得到未撤銷的設定檔）。

        ⚠️ `cleanup(retention_days)` 掃不到這裡：那支只走 `tts/` 底下的日期資料夾，
        參考音檔在 `voice-refs/`。沒有這支就等於「家屬按了撤銷、聲紋永遠留著」。
        """
        path = f"voice-refs/{elder_id}"
        try:
            self._transport.request(
                "DELETE",
                f"{self._base}/storage/v1/object/{self._bucket}",
                data=json.dumps({"paths": [path]}).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self._key}",
                    "Content-Type": "application/json",
                },
                timeout=self._timeout,
            )
        except TransportError as exc:
            logger.warning("參考音檔刪除失敗 elder_id=%s：%s", elder_id, exc)
        # 無論刪成功與否都清掉簽章快取：留著的話，撤銷後那個網址在效期內仍簽得出來。
        self._voice_url_cache.pop(path, None)

    def signed_url_for(self, path: str) -> str:
        """為 bucket 內**既有**物件簽一個短效讀取網址（長輩客製化聲音的參考音檔用）。

        與 `publish` 不同：這裡不上傳，只針對已存在的路徑取用網址。`voice_profiles`
        存的是物件路徑而非網址，正是為了每次現簽——存死的簽章 URL 會過期，過期後
        DGX 端下載失敗會讓整輪退化成純文字（長輩完全沒聲音）。

        ⚠️ 帶行程內快取：DGX 端拿到音檔後會自行快取，之後每輪其實用不到這個網址，
        但應用層無從得知對方的快取狀態，只能每輪都附上。實測簽一次約 384ms，且落在
        「長輩講完話到聽見回覆」的關鍵路徑上，故在效期內重用同一個網址。
        """
        now = self._clock()
        cached = self._voice_url_cache.get(path)
        if cached is not None and cached[1] > now:
            return cached[0]
        url = self._create_signed_url(path, expires_in=_VOICE_URL_TTL_SECONDS)
        # 提前 _VOICE_URL_REFRESH_MARGIN_SECONDS 失效：避免發出一個「就快過期」的網址，
        # 讓 DGX 端在下載途中才過期。
        self._voice_url_cache[path] = (
            url,
            now + timedelta(seconds=_VOICE_URL_TTL_SECONDS - _VOICE_URL_REFRESH_MARGIN_SECONDS),
        )
        return url

    def _create_signed_url(self, path: str, *, expires_in: int | None = None) -> str:
        sign_url = f"{self._base}/storage/v1/object/sign/{self._bucket}/{path}"
        seconds = self._signed_url_expires_seconds if expires_in is None else expires_in
        body = json.dumps({"expiresIn": seconds}).encode("utf-8")
        try:
            response = self._transport.request(
                "POST",
                sign_url,
                data=body,
                headers={
                    "Authorization": f"Bearer {self._key}",
                    "Content-Type": "application/json",
                },
                timeout=self._timeout,
            )
            payload = read_json(response)
        except TransportError as exc:
            raise AudioPublishError(f"音檔簽章失敗：{exc}") from exc
        signed_path = payload.get("signedURL") if isinstance(payload, dict) else None
        if not signed_path:
            raise AudioPublishError(f"音檔簽章回應缺 signedURL：{payload!r}")
        return f"{self._base}/storage/v1{signed_path}"

    def cleanup(self, *, retention_days: int) -> None:
        if retention_days <= 0:  # 0＝不清理（保留全部音檔本體）
            return
        cutoff = (self._clock() - timedelta(days=retention_days)).strftime("%Y%m%d")
        for folder in self._list_date_folders():
            if folder <= cutoff:
                self._delete_folder(folder)

    def _list_date_folders(self) -> list[str]:
        list_url = f"{self._base}/storage/v1/object/list/{self._bucket}"
        body = json.dumps({"prefix": f"{self._prefix}/", "limit": 1000}).encode("utf-8")
        try:
            response = self._transport.request(
                "POST",
                list_url,
                data=body,
                headers={
                    "Authorization": f"Bearer {self._key}",
                    "Content-Type": "application/json",
                },
                timeout=self._timeout,
            )
            rows = read_json(response)
        except TransportError as exc:
            raise AudioPublishError(f"音檔清單讀取失敗：{exc}") from exc
        return [r["name"] for r in rows if isinstance(r, dict) and "name" in r]

    def _list_files(self, folder: str) -> list[str]:
        """列出 {prefix}/{folder}/ 下的所有物件，回傳完整路徑（bucket 內 key）。"""
        list_url = f"{self._base}/storage/v1/object/list/{self._bucket}"
        prefix = f"{self._prefix}/{folder}/"
        body = json.dumps({"prefix": prefix, "limit": 1000}).encode("utf-8")
        response = self._transport.request(
            "POST",
            list_url,
            data=body,
            headers={"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"},
            timeout=self._timeout,
        )
        rows = read_json(response)
        return [f"{prefix}{r['name']}" for r in rows if isinstance(r, dict) and "name" in r]

    def _delete_folder(self, folder: str) -> None:
        """刪除 folder 下所有物件：先列出檔案，再一次 bulk DELETE。

        Supabase Storage 沒有「刪資料夾」這種操作（資料夾是虛擬的），
        必須先列出前綴下的實際物件 key，再對 bucket 層級的 DELETE 端點
        送出 {"paths": [...]}。任何一步失敗都只記警告，不中斷其他資料夾清理。
        """
        try:
            paths = self._list_files(folder)
            if not paths:
                return
            del_url = f"{self._base}/storage/v1/object/{self._bucket}"
            body = json.dumps({"paths": paths}).encode("utf-8")
            self._transport.request(
                "DELETE",
                del_url,
                data=body,
                headers={
                    "Authorization": f"Bearer {self._key}",
                    "Content-Type": "application/json",
                },
                timeout=self._timeout,
            )
        except TransportError as exc:
            logger.warning("音檔資料夾刪除失敗 folder=%s：%s", folder, exc)


def build_audio_publisher(
    settings,
    *,
    clock: Callable[[], datetime],
    new_id: Callable[[], str],
    prefix: str = "tts",
) -> SupabaseAudioPublisher:
    if not settings.supabase_url or not settings.supabase_service_key:
        raise AudioPublishError("TTS_BACKEND=dgx 需設定 SUPABASE_URL 與 SUPABASE_SERVICE_KEY")
    return SupabaseAudioPublisher(
        settings.supabase_url,
        settings.supabase_service_key,
        settings.audio_bucket,
        timeout=settings.audio_upload_timeout_seconds,
        clock=clock,
        new_id=new_id,
        prefix=prefix,
        signed_url_expires_seconds=settings.audio_signed_url_expires_seconds,
    )
