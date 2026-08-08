"""`scripts/kinsun.sh` 的自我說明與它實際支援的服務清單必須一致。

⚠️ 這條守的症狀是「`start web` 明明可以用，`usage` 卻查不到 web」——使用者只會
相信他看得到的那一份清單，於是新加的服務等於不存在。網頁版前端（P1）就是這樣
被漏掉的：`START_ORDER` 加了 `web`，usage 那一行沒跟著改。純文件漂移，程式一切
正常，所以不會有任何測試紅給你看——除非有這一條。

後半段（2026-08-07 起）守的是**模型預熱**：`start`／`restart` 必須等 ASR／TTS 的模型
真的載進 GPU 才算完成。實錄見 `_wait_model_warm` 上方的註解。
"""

from __future__ import annotations

import json
import re
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "kinsun.sh"


def _matched(pattern: str) -> str:
    match = re.search(pattern, SCRIPT.read_text(encoding="utf-8"), re.MULTILINE)
    assert match is not None, f"在 {SCRIPT.name} 找不到 {pattern}"
    return match.group(1)


def test_usage_的服務名清單與_start_order_逐項一致():
    # 全形空白（U+3000）也算空白，str.split() 切得動。
    usage_services = _matched(r"^服務名：(.+)$").split()
    start_order = _matched(r"^START_ORDER=\(([^)]*)\)").split()
    assert usage_services == start_order


# ── 模型預熱 ──────────────────────────────────────────────────────────


@pytest.fixture
def fake_healthz():
    """假的 `/healthz`：可隨測試切換 `model_loaded`，回傳 (port, 切換函式)。"""
    state = {"loaded": False}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler 的介面
            body = json.dumps({"status": "ok", "model_loaded": state["loaded"]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):  # 別把測試輸出洗掉
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server.server_address[1], lambda loaded: state.__setitem__("loaded", loaded)
    finally:
        server.shutdown()
        server.server_close()


def _wait_model_warm(port: int, run_dir: Path, *, alive: bool, timeout: int = 4) -> int:
    """在真正的 bash 裡跑 `_wait_model_warm asr <port>`，回傳它的結束碼。

    `alive` 決定要不要寫一個指向存活程序的 PID 檔——`is_running` 只看那個檔。
    """
    script = f"""
      source {SCRIPT} --help >/dev/null 2>&1
      RUN_DIR={run_dir}
      LOG_DIR={run_dir}
      {'echo $$ > "$RUN_DIR/asr.pid"' if alive else ""}
      _wait_model_warm asr {port}
    """
    return subprocess.run(
        ["bash", "-c", script],
        env={"PATH": "/usr/bin:/bin", "KINSUN_WARMUP_TIMEOUT": str(timeout)},
        capture_output=True,
        text=True,
    ).returncode


def test_模型已載入時預熱等待立刻成功(fake_healthz, tmp_path):
    port, set_loaded = fake_healthz
    set_loaded(True)
    assert _wait_model_warm(port, tmp_path, alive=True) == 0


def test_程序在載入中死掉回可重試碼(fake_healthz, tmp_path):
    # 這是 GPU 被別人占滿時的形狀：preload 在 lifespan 拋 CUDA OOM，uvicorn 起不來就退出。
    # 必須與「還在載、只是慢」分得開——後者重試只會更慢，見 _launch_warm。
    port, _ = fake_healthz
    assert _wait_model_warm(port, tmp_path, alive=False) == 1


def test_程序活著但逾時未就緒回不可重試碼(fake_healthz, tmp_path):
    port, _ = fake_healthz  # 一直回 model_loaded=false
    assert _wait_model_warm(port, tmp_path, alive=True, timeout=3) == 2


def test_asr_與_tts_啟動時都帶預熱旗標():
    # ⚠️ 這條守的正是 2026-08-07 的破口：TTS 有 TTS_PRELOAD=1、ASR 沒有，於是
    # restart 後長輩的第一句話才觸發 ASR 載模型，撞上滿載的共用 GPU → CUDA OOM。
    body = SCRIPT.read_text(encoding="utf-8")
    launch_asr = re.search(r"^launch_asr\(\) \{(.+?)^\}", body, re.MULTILINE | re.DOTALL)
    launch_tts = re.search(r"^launch_tts\(\) \{(.+?)^\}", body, re.MULTILINE | re.DOTALL)
    assert launch_asr and launch_tts
    assert "ASR_PRELOAD" in launch_asr.group(1)
    assert "TTS_PRELOAD" in launch_tts.group(1)


def test_usage_有說明預熱可調的環境變數():
    # 與上面那條「服務名清單」同一個道理：使用者只調得動他看得到的旋鈕。
    usage = _matched(r"環境變數：\n((?:  .+\n)+)")
    for key in ("KINSUN_WARMUP_TIMEOUT", "KINSUN_WARMUP_RETRIES"):
        assert key in usage, f"usage 的環境變數段沒有 {key}"
