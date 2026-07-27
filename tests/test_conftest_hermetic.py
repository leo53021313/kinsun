"""測試行程密封：正式金鑰不得進入測試行程。

⚠️ 為什麼需要這一層（2026-07-27 實測）：`conftest.py` 原本無條件 `load_dotenv()`，把
正式 `.env` 的 106 個鍵灌進測試行程——正式 Supabase 連線串、LINE token、Gemini 金鑰、
admin 金鑰全都在裡面。於是每個測試都得自己記得覆寫，而**已經漏掉一個**：
`test_app.py` 的 `_REQUIRED_ENV` 覆寫了 `TTS_BACKEND` 卻沒覆寫 `ASR_BACKEND`，
`build_app()` 在單元測試裡真的建出了指向正式 DGX 的 `DgxAsrClient`。

正確的界線不是「每個測試自己小心」，是「測試行程根本拿不到」。CI 本來就在沒有 `.env`
的環境跑全套且長期全綠（.github/workflows/ci.yml 的 test job 一個 env 都沒設），
證明沒有任何測試真的需要正式金鑰——密封只是讓本機對齊 CI。
"""

from __future__ import annotations

import os

import conftest as _conftest
import pytest

# 從 .env.example 取「這個應用會讀的鍵」全集（單一真實來源），扣掉測試旗標。
_APP_KEYS = sorted(_conftest.APP_ENV_KEYS - _conftest.TEST_ONLY_KEYS)


def test_env_example_is_the_source_of_truth():
    """清單得自 .env.example，不是人工維護的第二份名單——否則新增金鑰會漏掉。"""
    assert len(_APP_KEYS) > 50, "沒讀到 .env.example，密封等於沒做"
    for key in ("GEMINI_API_KEY", "LINE_CHANNEL_ACCESS_TOKEN", "DATABASE_URL", "ADMIN_API_KEY"):
        assert key in _APP_KEYS


@pytest.mark.parametrize("key", _APP_KEYS)
def test_no_production_key_reaches_the_test_process(key):
    """逐鍵斷言：測試行程的環境變數裡不得有任何正式設定。"""
    assert key not in os.environ, f"{key} 洩漏進測試行程"


def test_test_only_flags_still_pass_through():
    """整合測試靠這兩把啟用，密封不可把它們一起擋掉。"""
    assert _conftest.TEST_ONLY_KEYS == {"KINSUN_IT", "KINSUN_TEST_DATABASE_URL"}


def test_d69_guard_still_sees_the_production_url():
    """⚠️ 密封最容易踩壞的東西：D-69 防呆原本拿 `os.environ["DATABASE_URL"]` 比對，
    金鑰一清掉就變成跟空字串比、**靜默失效**——防呆看起來還在，其實不再擋任何東西。

    故改由 `_production_database_url()` 直接讀 .env 檔（不進 os.environ）。
    """
    assert "DATABASE_URL" not in os.environ  # 已密封
    url = _conftest._production_database_url()
    assert url.startswith("postgres"), "讀不到正式庫 URL，D-69 防呆會靜默失效"


def test_settings_build_offline_without_the_dotenv():
    """密封後 config 預設值必須仍是離線安全的替身，否則測試會去連真服務。"""
    from kinsun.config import ConfigError, load_settings

    with pytest.raises(ConfigError, match="GEMINI_API_KEY|LINE_CHANNEL"):
        load_settings({})  # 缺必要金鑰即 fail-fast，不會靜默拿到正式值
