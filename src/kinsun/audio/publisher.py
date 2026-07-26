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

    def _create_signed_url(self, path: str) -> str:
        sign_url = f"{self._base}/storage/v1/object/sign/{self._bucket}/{path}"
        body = json.dumps({"expiresIn": self._signed_url_expires_seconds}).encode("utf-8")
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
