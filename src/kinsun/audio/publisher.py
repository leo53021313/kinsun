"""音檔發佈：把 TTS 音檔上傳 Supabase Storage 公開 bucket，回公開 URL。

標準庫 urllib（不加 supabase SDK）；service key 走環境變數。
路徑帶日期資料夾 tts/{yyyymmdd}/，清理只刪過期資料夾。
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Protocol

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
    ) -> None:
        self._base = base_url.rstrip("/")
        self._key = service_key
        self._bucket = bucket
        self._timeout = timeout
        self._clock = clock
        self._new_id = new_id

    def _object_path(self, name: str) -> str:
        return f"tts/{self._clock().strftime('%Y%m%d')}/{name}"

    def publish(self, audio: bytes, *, content_type: str) -> str:
        path = self._object_path(f"{self._new_id()}.m4a")
        upload_url = f"{self._base}/storage/v1/object/{self._bucket}/{path}"
        request = urllib.request.Request(
            upload_url,
            data=audio,
            headers={
                "Authorization": f"Bearer {self._key}",
                "Content-Type": content_type,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                response.read()
        except (urllib.error.URLError, OSError) as exc:
            raise AudioPublishError(f"音檔上傳失敗：{exc}") from exc
        return f"{self._base}/storage/v1/object/public/{self._bucket}/{path}"

    def cleanup(self, *, retention_days: int) -> None:
        cutoff = (self._clock() - timedelta(days=retention_days)).strftime("%Y%m%d")
        for folder in self._list_date_folders():
            if folder <= cutoff:
                self._delete_folder(folder)

    def _list_date_folders(self) -> list[str]:
        list_url = f"{self._base}/storage/v1/object/list/{self._bucket}"
        body = json.dumps({"prefix": "tts/", "limit": 1000}).encode("utf-8")
        request = urllib.request.Request(
            list_url,
            data=body,
            headers={"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                rows = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            raise AudioPublishError(f"音檔清單讀取失敗：{exc}") from exc
        return [r["name"] for r in rows if isinstance(r, dict) and "name" in r]

    def _delete_folder(self, folder: str) -> None:
        del_url = f"{self._base}/storage/v1/object/{self._bucket}/tts/{folder}"
        request = urllib.request.Request(
            del_url,
            headers={"Authorization": f"Bearer {self._key}"},
            method="DELETE",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                response.read()
        except (urllib.error.URLError, OSError) as exc:
            logger.warning("音檔資料夾刪除失敗 folder=%s：%s", folder, exc)


def build_audio_publisher(
    settings, *, clock: Callable[[], datetime], new_id: Callable[[], str]
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
    )
