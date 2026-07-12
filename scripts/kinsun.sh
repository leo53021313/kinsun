#!/usr/bin/env bash
#
# kinsun.sh — 金孫全功能服務堆疊啟停腳本（DGX Spark / Linux）
#
#   scripts/kinsun.sh start     背景啟動全部服務
#   scripts/kinsun.sh stop      關閉全部服務
#   scripts/kinsun.sh status    檢視各服務狀態
#   scripts/kinsun.sh restart   先 stop 再 start
#
# 設計文件：docs/superpowers/specs/2026-07-03-全功能啟停腳本-design.md
#
# 管理的程序：ASR(8001)、TTS(8002)、Webhook(8000)、Scheduler、前端 LIFF(5173)、ngrok。
# 每個程序以 setsid 起在獨立 process group，log 寫 logs/<name>.log、PID 寫 .run/<name>.pid。
# 可選元件（TTS/前端/ngrok）缺依賴時只警告並跳過，不中斷整體。

set -o pipefail

# ── 路徑 ──────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$ROOT/logs"
RUN_DIR="$ROOT/.run"

# 啟動順序（GPU 服務先起、載模型較慢）；停止則反序。
START_ORDER=(asr tts webhook scheduler frontend ngrok)
STOP_ORDER=(ngrok frontend scheduler webhook tts asr)

declare -A PORT=([asr]=8001 [tts]=8002 [webhook]=8000 [frontend]=5173)

# ── 輸出小工具 ────────────────────────────────────────────────────────
if [ -t 1 ]; then
  C_INFO=$'\033[36m'; C_OK=$'\033[32m'; C_WARN=$'\033[33m'; C_ERR=$'\033[31m'; C_OFF=$'\033[0m'
else
  C_INFO=""; C_OK=""; C_WARN=""; C_ERR=""; C_OFF=""
fi
info() { printf '%s[kinsun]%s %s\n' "$C_INFO" "$C_OFF" "$*"; }
ok()   { printf '%s[  ok  ]%s %s\n' "$C_OK"   "$C_OFF" "$*"; }
warn() { printf '%s[ warn ]%s %s\n' "$C_WARN" "$C_OFF" "$*" >&2; }
err()  { printf '%s[ err  ]%s %s\n' "$C_ERR"  "$C_OFF" "$*" >&2; }

# ── .env 讀取（只取單一鍵值，不匯入整份，避免污染環境）─────────────────
read_env() {
  local key="$1" file="$ROOT/.env" line val
  [ -f "$file" ] || return 0
  line="$(grep -E "^[[:space:]]*${key}=" "$file" | tail -n1 || true)"
  [ -n "$line" ] || return 0
  val="${line#*=}"
  val="${val%$'\r'}"
  case "$val" in
    \"*\") val="${val%\"}"; val="${val#\"}" ;;
    \'*\') val="${val%\'}"; val="${val#\'}" ;;
  esac
  printf '%s' "$val"
}

# ── 程序存活 / 埠 / 健康探測 ─────────────────────────────────────────
_pid_of() { local f="$RUN_DIR/$1.pid"; [ -f "$f" ] && cat "$f" 2>/dev/null; }

is_running() {
  local pid; pid="$(_pid_of "$1")"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

_port_open() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltn 2>/dev/null | grep -q ":${port}[[:space:]]"
  elif command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
  else
    (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null && exec 3>&-
  fi
}

_http_ok() { command -v curl >/dev/null 2>&1 && curl -fsS --max-time 2 "$1" >/dev/null 2>&1; }

# ── 背景啟動：setsid 起在新 process group、log 導向、寫 PID ─────────────
# 由 session leader 自行把 $$ 寫進 PID 檔——不倚賴 $!。因為 setsid 在啟用
# job control 的 shell 下會 fork，$! 會落在隨即結束的 setsid 父程序上，導致
# PID 檔指向死程序、真正的服務變孤兒。改由 setsid 內的 bash 寫自己的 $$
# 再 exec 成目標程序（pid 與 process group 不變），停止時才能整組收乾淨。
_bg() {
  local name="$1"; shift
  local logfile="$LOG_DIR/$name.log" pidfile="$RUN_DIR/$name.pid"
  printf '=== %s start %s ===\n' "$name" "$(date '+%Y-%m-%d %H:%M:%S')" >> "$logfile"
  rm -f "$pidfile"
  if command -v setsid >/dev/null 2>&1; then
    setsid bash -c 'echo $$ > "$1"; shift; exec "$@"' _ "$pidfile" "$@" >> "$logfile" 2>&1 &
  else
    # 無 setsid（多為非 Linux）：退回一般背景執行，pid 取 $!，停止僅能對單一 pid。
    "$@" >> "$logfile" 2>&1 &
    echo $! > "$pidfile"
  fi
}

# 啟動前共通檢查：已在跑就跳過、埠被占用就跳過。回傳 0 表示可啟動。
_precheck() {
  local name="$1" port="${2:-}"
  if is_running "$name"; then
    warn "$name：已在執行 (PID $(_pid_of "$name"))，跳過"
    return 1
  fi
  if [ -n "$port" ] && _port_open "$port"; then
    warn "$name：埠 $port 已被占用（可能已在跑或被他程序占用），跳過"
    return 1
  fi
  return 0
}

# ── 各服務啟動器（缺依賴 → 警告並跳過）───────────────────────────────
launch_asr() {
  local venv="$ROOT/services/asr/.venv"
  _precheck asr "${PORT[asr]}" || return 0
  if [ ! -x "$venv/bin/python" ]; then
    warn "ASR：找不到 $venv（請先在 DGX 建置 ASR 環境），跳過"
    return 0
  fi
  info "啟動 ASR (port ${PORT[asr]})…"
  _bg asr "$venv/bin/python" -m uvicorn services.asr.server:app --host 0.0.0.0 --port "${PORT[asr]}"
}

launch_tts() {
  local envfile="$ROOT/services/tts/.env.tts"
  _precheck tts "${PORT[tts]}" || return 0
  if [ ! -f "$envfile" ]; then
    warn "TTS：找不到 $envfile（照 services/tts/.env.tts.example 建立後才會啟動），跳過"
    return 0
  fi
  info "啟動 TTS (port ${PORT[tts]})…"
  (
    set -a; . "$envfile"; set +a
    local py="${TTS_PYTHON:-python}"
    if ! command -v "$py" >/dev/null 2>&1 && [ ! -x "$py" ]; then
      warn "TTS：TTS_PYTHON=$py 不可執行（請於 .env.tts 指向 CosyVoice 環境的 python），跳過"
      exit 0
    fi
    _bg tts "$py" -m uvicorn services.tts.server:app --host 0.0.0.0 --port "${PORT[tts]}"
  )
}

launch_webhook() {
  _precheck webhook "${PORT[webhook]}" || return 0
  if ! command -v uv >/dev/null 2>&1; then
    warn "Webhook：找不到 uv，跳過（請先安裝 uv）"
    return 0
  fi
  info "啟動 Webhook (port ${PORT[webhook]})…"
  local cmd=(uv run uvicorn --app-dir src "kinsun.app:build_app" --factory --host 0.0.0.0 --port "${PORT[webhook]}")
  if [ "${KINSUN_RELOAD:-0}" = "1" ]; then
    cmd+=(--reload)
    info "Webhook：已啟用 --reload（KINSUN_RELOAD=1）"
  else
    # 多 worker（✅ D-20 丙-3）：對講機一請求佔住 ASR→LLM→TTS 全鏈路，
    # 單進程會整台卡住。WEB_WORKERS 為部署層鍵（不經 config.py），預設 2。
    # ⚠️ 連線總量（✅ 庚-26）：WEB_WORKERS×DATABASE_POOL_MAX_SIZE(5)＋排程 worker 5
    #    ≤ Supabase 直連上限 60 → WEB_WORKERS 安全上限約 8（還要留 CLI 餘裕）。
    # 連線池評估：每 worker 池上限 5 ＋ scheduler 5 ＝ 15 連線，Supabase 額度內。
    # 注意：--reload 與 --workers 互斥（uvicorn 限制），開發模式維持單進程。
    cmd+=(--workers "${WEB_WORKERS:-2}")
    info "Webhook：多 worker 啟動（WEB_WORKERS=${WEB_WORKERS:-2}）"
  fi
  _bg webhook "${cmd[@]}"
}

launch_scheduler() {
  _precheck scheduler || return 0
  if ! command -v uv >/dev/null 2>&1; then
    warn "Scheduler：找不到 uv，跳過"
    return 0
  fi
  info "啟動 Scheduler…"
  (
    export PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}"
    _bg scheduler uv run python -m kinsun.scheduler
  )
}

launch_frontend() {
  _precheck frontend "${PORT[frontend]}" || return 0
  if ! command -v npm >/dev/null 2>&1; then
    warn "前端：找不到 npm，跳過"
    return 0
  fi
  if [ ! -d "$ROOT/frontend/node_modules" ]; then
    warn "前端：frontend/node_modules 不存在，請先 npm --prefix frontend install，跳過"
    return 0
  fi
  [ -f "$ROOT/frontend/.env" ] || warn "前端：frontend/.env 不存在（VITE_LIFF_ID 未設，LIFF 於瀏覽器初始化會失敗），仍照常啟動 dev server"
  info "啟動 前端 LIFF dev (port ${PORT[frontend]})…"
  _bg frontend npm --prefix "$ROOT/frontend" run dev
}

launch_ngrok() {
  _precheck ngrok || return 0
  if ! command -v ngrok >/dev/null 2>&1; then
    warn "ngrok：找不到 ngrok，跳過"
    return 0
  fi
  info "啟動 ngrok（對外 port ${PORT[webhook]}）…"
  (
    local token domain
    token="$(read_env NGROK_AUTHTOKEN)"
    domain="$(read_env NGROK_DOMAIN)"
    [ -n "$token" ] && export NGROK_AUTHTOKEN="$token"
    local cmd=(ngrok http "${PORT[webhook]}" --log stdout)
    if [ -n "$domain" ]; then
      cmd+=(--domain "$domain")
    else
      warn "ngrok：.env 未設 NGROK_DOMAIN，改用臨時網域"
    fi
    _bg ngrok "${cmd[@]}"
  )
}

# ── 子指令 ────────────────────────────────────────────────────────────
cmd_start() {
  cd "$ROOT" || { err "無法進入專案根目錄 $ROOT"; exit 1; }
  if [ ! -f "$ROOT/pyproject.toml" ] || [ ! -d "$ROOT/src/kinsun" ]; then
    err "看起來不在金孫專案根目錄（缺 pyproject.toml 或 src/kinsun），中止"
    exit 1
  fi
  mkdir -p "$LOG_DIR" "$RUN_DIR"
  info "啟動金孫服務堆疊…"
  for name in "${START_ORDER[@]}"; do
    "launch_${name}"
  done
  info "等待服務就緒…"
  sleep 2
  echo
  cmd_status
  echo
  info "log 目錄：$LOG_DIR"
  info "停止全部：scripts/kinsun.sh stop"
}

stop_one() {
  local name="$1"
  local pidfile="$RUN_DIR/$name.pid"
  local pid i
  if [ ! -f "$pidfile" ]; then
    return 1
  fi
  pid="$(cat "$pidfile" 2>/dev/null)"
  if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
    warn "$name：無存活程序，清除舊 PID 檔"
    rm -f "$pidfile"
    return 1
  fi
  info "$name：送 SIGTERM (PID $pid)…"
  kill -TERM -- -"$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null
  i=0
  while kill -0 "$pid" 2>/dev/null && [ "$i" -lt 20 ]; do
    sleep 0.5; i=$((i + 1))
  done
  if kill -0 "$pid" 2>/dev/null; then
    warn "$name：逾時未退，送 SIGKILL"
    kill -KILL -- -"$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null
    sleep 0.5
  fi
  rm -f "$pidfile"
  ok "$name：已停止"
  return 0
}

cmd_stop() {
  info "關閉金孫服務堆疊…"
  local stopped=0
  for name in "${STOP_ORDER[@]}"; do
    if stop_one "$name"; then
      stopped=$((stopped + 1))
    fi
  done
  if [ "$stopped" -eq 0 ]; then
    info "沒有偵測到執行中的服務。"
  else
    ok "已停止 $stopped 個服務。"
  fi
}

# 回傳某服務的健康／埠說明字串
_health_note() {
  local name="$1"
  local port="${PORT[$name]:-}"
  case "$name" in
    asr|tts)
      if _http_ok "http://127.0.0.1:${port}/healthz"; then echo "healthz OK :${port}"
      elif _port_open "$port"; then echo "埠開啟、模型載入中 :${port}"
      else echo "—"; fi ;;
    webhook|frontend)
      if _port_open "$port"; then echo "listening :${port}"; else echo "—"; fi ;;
    scheduler)
      echo "（無對外埠）" ;;
    ngrok)
      local d; d="$(read_env NGROK_DOMAIN)"
      if [ -n "$d" ]; then echo "https://$d"; else echo "臨時網域（見 log）"; fi ;;
    *) echo "—" ;;
  esac
}

cmd_status() {
  printf '%-11s %-9s %-8s %s\n' "SERVICE" "STATE" "PID" "PORT / HEALTH"
  printf '%-11s %-9s %-8s %s\n' "-------" "-----" "---" "-------------"
  local name state pid note dot port
  for name in "${START_ORDER[@]}"; do
    port="${PORT[$name]:-}"
    if is_running "$name"; then
      state="RUNNING"; pid="$(_pid_of "$name")"; dot="${C_OK}●${C_OFF}"
      note="$(_health_note "$name")"
    elif [ -n "$port" ] && _port_open "$port"; then
      # 埠有服務但無本腳本的 PID 檔——多半是你手動另外啟動的。
      state="EXTERNAL"; pid="-"; dot="${C_WARN}●${C_OFF}"
      note="$(_health_note "$name")（非本腳本啟動）"
    else
      state="STOPPED"; pid="-"; dot="${C_ERR}●${C_OFF}"
      note="—"
    fi
    printf '%b %-9s %-9s %-8s %s\n' "$dot" "$name" "$state" "$pid" "$note"
  done
}

usage() {
  cat <<EOF
用法：scripts/kinsun.sh <指令>

指令：
  start     背景啟動全部服務（ASR、TTS、Webhook、Scheduler、前端、ngrok）
  stop      關閉全部服務
  status    檢視各服務狀態（PID／埠／健康）
  restart   先 stop 再 start

環境變數：
  KINSUN_RELOAD=1   Webhook 啟用 --reload（開發用；預設關）

log：logs/<service>.log　PID：.run/<service>.pid
EOF
}

# ── 進入點 ────────────────────────────────────────────────────────────
case "${1:-}" in
  start)   cmd_start ;;
  stop)    cmd_stop ;;
  status)  cmd_status ;;
  restart) cmd_stop; echo; cmd_start ;;
  ""|-h|--help|help) usage ;;
  *) err "未知指令：$1"; echo; usage; exit 2 ;;
esac
