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
# 管理的程序：ASR(8001)、TTS(8002)、Webhook(8000)、Scheduler、前端 LIFF(5173)、
#             App Expo dev server(8081)、ngrok。
# 每個程序以 setsid 起在獨立 process group，log 寫 logs/<name>.log、PID 寫 .run/<name>.pid。
# 可選元件（TTS/前端/App/ngrok）缺依賴時只警告並跳過，不中斷整體。

set -o pipefail

# ── 路徑 ──────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$ROOT/logs"
RUN_DIR="$ROOT/.run"

# 啟動順序（GPU 服務先起、載模型較慢）；停止則反序。
# opik＝Opik 公開隧道（Cloudflare Quick Tunnel）；隨堆疊一起起停。啟動需本機 Opik（:5273）
# 已在跑，否則 launch_opik 會警告並略過。⚠️ 公開且無認證，見 launch_opik 與 docs/dev/14。
START_ORDER=(asr tts webhook scheduler frontend app ngrok opik)
STOP_ORDER=(opik ngrok app frontend scheduler webhook tts asr)

declare -A PORT=([asr]=8001 [tts]=8002 [webhook]=8000 [frontend]=5173 [app]=8081)

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

# 本機區網 IP（Expo Go 掃的 exp:// 位址要用它）。取預設路由的來源位址，
# 避開 docker 橋接（172.17.x）與 Tailscale（100.x）等非區網介面。
_lan_ip() {
  ip route get 1.1.1.1 2>/dev/null |
    awk '{for (i = 1; i <= NF; i++) if ($i == "src") { print $(i + 1); exit }}'
}

# 取 log 檔「最後一次啟動」之後的內容——避免抓到上一輪殘留的訊息。
_last_run_log() {
  local f="$1"
  [ -f "$f" ] || return 0
  awk '/^=== .* start /{buf = ""} {buf = buf $0 ORS} END{printf "%s", buf}' "$f"
}

# Expo Go 要掃的位址。Expo 只在互動終端印 QR／網址，背景啟動時 log 裡一個字都沒有——
# 改問 Metro 的 manifest：launchAsset.url 的 host 就是手機實際要連的位置
# （tunnel 模式為 xxx.exp.direct、LAN 模式為 區網IP:8081），兩種模式都準。
_expo_url() {
  command -v curl >/dev/null 2>&1 || return 0
  local manifest host
  manifest="$(curl -s --max-time 3 \
    -H 'expo-platform: ios' -H 'accept: application/expo+json,application/json' \
    "http://127.0.0.1:${PORT[app]}/" 2>/dev/null)" || return 0
  host="$(printf '%s' "$manifest" |
    grep -o '"launchAsset":{[^}]*"url":"[^"]*"' |
    grep -o '"url":"[^"]*"' | cut -d'"' -f4 |
    sed -E 's#^https?://##; s#/.*$##')"
  [ -n "$host" ] && printf 'exp://%s' "$host"
}

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

# App（Expo dev server）：手機裝 Expo Go 掃 status 顯示的 exp:// 位址即可開發，免簽章。
#
# 預設走 tunnel（✅ 團隊測試手機與 DGX 從不在同一個 Wi-Fi）：Expo 經 exp.direct 反向
# 隧道對外，任何網路的手機都連得到。KINSUN_EXPO_TUNNEL=0 可切回 LAN（僅同網段可用，
# 但啟動快、不依賴外部服務）。
#
# tunnel 偶發啟動失敗（exp.direct 端 "remote gone away"），失敗時 Expo 會整個退出、
# 連 Metro 都不留——故此處等到 tunnel 就緒才算數，失敗自動重試一次。
launch_app() {
  _precheck app "${PORT[app]}" || return 0
  if ! command -v npm >/dev/null 2>&1; then
    warn "App：找不到 npm，跳過"
    return 0
  fi
  if [ ! -d "$ROOT/app/node_modules" ]; then
    warn "App：app/node_modules 不存在，請先 npm --prefix app install，跳過"
    return 0
  fi
  [ -f "$ROOT/app/.env" ] ||
    warn "App：app/.env 不存在（EXPO_PUBLIC_API_URL 未設，App 呼叫後端會失敗），仍照常啟動"

  if [ "${KINSUN_EXPO_TUNNEL:-1}" != "1" ]; then
    # LAN 模式：釘住 packager hostname，否則 Expo 可能在多網卡（docker／Tailscale）上挑錯
    # 介面，手機掃到位址也抓不到 bundle。
    info "啟動 App Expo dev server（LAN 模式，需與手機同網段，port ${PORT[app]})…"
    (
      local ip
      ip="$(_lan_ip)"
      if [ -n "$ip" ]; then
        export REACT_NATIVE_PACKAGER_HOSTNAME="$ip"
      else
        warn "App：抓不到區網 IP，Expo 將自行挑選介面（手機連不上就拿掉 KINSUN_EXPO_TUNNEL=0）"
      fi
      _bg app npm --prefix "$ROOT/app" run start
    )
    return 0
  fi

  info "啟動 App Expo dev server（tunnel 模式，對外可連，port ${PORT[app]})…"
  local tries="${KINSUN_EXPO_TUNNEL_RETRIES:-8}" attempt
  for attempt in $(seq 1 "$tries"); do
    _bg app npm --prefix "$ROOT/app" run start -- --tunnel
    if _wait_expo_tunnel; then
      ok "App：tunnel 就緒（第 ${attempt}／${tries} 次嘗試）"
      return 0
    fi
    _reap_app  # 收乾淨再重來，否則下一次會撞上「埠已被占用」而跳過（見 _reap_app）
    if [ "$attempt" -lt "$tries" ]; then
      warn "App：tunnel 建立失敗（exp.direct 抽風），第 $((attempt + 1))／${tries} 次重試…"
      sleep 3
    fi
  done
  err "App：tunnel 連試 ${tries} 次都失敗——exp.direct 可能正在故障。"
  err "     稍後重試：scripts/kinsun.sh restart app"
  err "     或改走區網（僅手機與 DGX 同網段可用）：KINSUN_EXPO_TUNNEL=0 scripts/kinsun.sh restart app"
  return 0
}

# tunnel 失敗後的殘骸清理。為何不能只用 stop_one：tunnel 失敗時 Expo 主進程（PID 檔記的
# 那個）會自己退出，但 Metro 子進程可能還占著 8081；stop_one 見 leader 已死就只清 PID 檔、
# 不送 group 訊號，殘骸於是留下，下一次重試撞上「埠已被占用」直接跳過——重試等於白做。
# 這裡對整個 process group 補一刀，再從埠反查漏網的占用者（Expo 的 node 進程會把執行緒名
# 改成 MainThread，pkill -f 抓不到，只能靠埠反查）。
_reap_app() {
  local pidfile="$RUN_DIR/app.pid" pid owner i
  pid="$(cat "$pidfile" 2>/dev/null)"
  [ -n "$pid" ] && kill -KILL -- -"$pid" 2>/dev/null
  rm -f "$pidfile"
  for i in 1 2 3 4 5; do
    _port_open "${PORT[app]}" || return 0
    owner="$(ss -ltnp 2>/dev/null | grep ":${PORT[app]} " |
      grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2)"
    [ -n "$owner" ] && kill -KILL "$owner" 2>/dev/null
    sleep 1
  done
}

# 等 Expo 的 tunnel 就緒：成功回 0；明確失敗或逾時回 1。
#
# exp.direct 的失敗是「秒級即答」（remote gone away，約 4 秒內），成功也只要數秒——
# 實測單次成功率僅約四成，但因為判定極快，重試的成本很低：預設連試 8 次，理論上
# 全軍覆沒的機率不到 2%，最壞情況約一分鐘。這是不引入第三方隧道的前提下，讓 App
# 每次 start／restart 都能起來的關鍵。
#
# 只讀本輪 log（_last_run_log），避免撞到上一輪殘留的 "Tunnel ready"。
_wait_expo_tunnel() {
  local i log
  for i in $(seq 1 30); do
    log="$(_last_run_log "$LOG_DIR/app.log")"
    case "$log" in
      *"Tunnel ready"*) return 0 ;;
      *"failed to start tunnel"*) return 1 ;;
    esac
    sleep 2
  done
  return 1
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
# 服務名合法性檢查——打錯字時直接說清楚，不要默默什麼都沒做。
# Opik 公開隧道（Cloudflare Quick Tunnel → :5273）。opt-in：不在 START_ORDER，
# 故 `start`（全部）不會自動開；需遠端看 Opik 時才 `start opik`，看完 `stop opik`。
# ⚠️ 免網域的 Quick Tunnel＝臨時網址（每次重啟會變）且【公開、無認證】。真實長輩
# 資料進入 Opik 前切勿長時間開啟（見 docs/dev/14）。網址由 status 動態顯示。
launch_opik() {
  _precheck opik || return 0
  if ! command -v cloudflared >/dev/null 2>&1; then
    warn "opik：找不到 cloudflared，跳過（安裝見 docs/dev/14）"
    return 0
  fi
  if ! _port_open 5273; then
    warn "opik：本機 Opik（:5273）未啟動，請先 cd /home/leo29/opik && ./opik.sh"
    return 0
  fi
  warn "opik 隧道為【公開且無認證】的臨時網址；看完請 stop opik，勿在有真實長輩資料時長開。"
  info "啟動 Opik 公開隧道（Cloudflare Quick Tunnel → :5273）…"
  _bg opik cloudflared tunnel --url http://localhost:5273 --no-autoupdate
}

# 從隧道 log 取當前 trycloudflare 網址（每次重啟會變，取最後一個）。
_opik_tunnel_url() {
  local f="$LOG_DIR/opik.log"
  [ -f "$f" ] || return 0
  grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$f" 2>/dev/null | tail -1
}

_assert_service() {
  local name="$1" s
  for s in "${START_ORDER[@]}"; do
    [ "$s" = "$name" ] && return 0
  done
  err "未知服務：$name"
  err "可用服務：${START_ORDER[*]}"
  exit 2
}

cmd_start() {
  local only="${1:-}"
  cd "$ROOT" || { err "無法進入專案根目錄 $ROOT"; exit 1; }
  if [ ! -f "$ROOT/pyproject.toml" ] || [ ! -d "$ROOT/src/kinsun" ]; then
    err "看起來不在金孫專案根目錄（缺 pyproject.toml 或 src/kinsun），中止"
    exit 1
  fi
  mkdir -p "$LOG_DIR" "$RUN_DIR"
  local targets=("${START_ORDER[@]}")
  if [ -n "$only" ]; then
    _assert_service "$only"
    targets=("$only")
    info "啟動服務：$only"
  else
    info "啟動金孫服務堆疊…"
  fi
  for name in "${targets[@]}"; do
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
  local only="${1:-}"
  local targets=("${STOP_ORDER[@]}")
  if [ -n "$only" ]; then
    _assert_service "$only"
    targets=("$only")
    info "關閉服務：$only"
  else
    info "關閉金孫服務堆疊…"
  fi
  local stopped=0
  for name in "${targets[@]}"; do
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

cmd_restart() {
  local only="${1:-}"
  cmd_stop "$only"
  echo
  cmd_start "$only"
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
    app)
      if _port_open "$port"; then
        local url
        url="$(_expo_url)"
        # 埠開了但問不到位址：多半是 Metro 還在暖機（或 tunnel 尚未接上）。
        echo "${url:-啟動中… :${port}}"
      else
        echo "—"
      fi ;;
    scheduler)
      echo "（無對外埠）" ;;
    ngrok)
      local d; d="$(read_env NGROK_DOMAIN)"
      if [ -n "$d" ]; then echo "https://$d"; else echo "臨時網域（見 log）"; fi ;;
    opik)
      local u; u="$(_opik_tunnel_url)"
      echo "${u:-啟動中…（見 logs/opik.log）}　⚠公開無認證" ;;
    *) echo "—" ;;
  esac
}

# Opik 工程觀測後台連結（服務由 /home/leo29/opik 的 ./opik.sh 獨立管理，本腳本只顯示）。
# UI 網址由 OPIK_URL_OVERRIDE 去掉 /api 推得（預設 http://localhost:5273）；真實環境變數優先，
# 否則讀 .env。同時顯示服務是否在跑與 app 端旗標，讓「有連結但沒開觀測」不會被誤會。
_opik_note() {
  local url ui port state enabled flag
  url="${OPIK_URL_OVERRIDE:-$(read_env OPIK_URL_OVERRIDE)}"
  ui="${url:-http://localhost:5273/api}"; ui="${ui%/api}"; ui="${ui%/}"
  port="$(printf '%s' "$ui" | sed -n 's#.*:\([0-9][0-9]*\).*#\1#p')"; [ -n "$port" ] || port=5273
  if _port_open "$port"; then
    state="${C_OK}● 執行中${C_OFF}"
  else
    state="${C_ERR}● 未啟動${C_OFF}（cd /home/leo29/opik && ./opik.sh）"
  fi
  enabled="${OPIK_ENABLED:-$(read_env OPIK_ENABLED)}"
  case "$(printf '%s' "$enabled" | tr '[:upper:]' '[:lower:]')" in
    ""|0|false|no|off) flag="OPIK_ENABLED=false（app 不送 trace）" ;;
    *)                 flag="OPIK_ENABLED=true（app 送 trace）" ;;
  esac
  # 本機後台連結＋旗標；公開隧道（服務 opik）狀態與網址由上方服務表的 opik 那列顯示。
  printf '%s[kinsun]%s Opik 觀測後台（本機）：%s  %b  |  %s\n' "$C_INFO" "$C_OFF" "$ui" "$state" "$flag"
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
  echo
  _opik_note
}

usage() {
  cat <<EOF
用法：scripts/kinsun.sh <指令>

指令（皆可只指定單一服務）：
  start [服務]     背景啟動全部或指定服務
  stop [服務]      關閉全部或指定服務
  restart [服務]   先 stop 再 start
  status           檢視各服務狀態（PID／埠／健康）＋ Opik 觀測後台連結

服務名：asr　tts　webhook　scheduler　frontend　app　ngrok　opik

Opik 工程觀測：status／start 結尾會印出本機後台連結（預設 http://localhost:5273）與服務狀態。
  服務本身由 /home/leo29/opik 的 ./opik.sh 獨立管理；app 要送 trace 需設 OPIK_ENABLED=true。

Opik 公開隧道（服務名 opik，Cloudflare Quick Tunnel → :5273，遠端／隊友檢視）：
  隨 start／stop／restart（全部）一起起停；也可 start opik／stop opik 單獨操作。
  status 的 opik 那列顯示當前公開網址（每次重啟會變）。需本機 Opik（:5273）已在跑才會起。
  ⚠️ Quick Tunnel 免網域但【公開、無認證】——真實長輩資料進入 Opik 前，
     請改用正式版（Cloudflare 網域＋Access，見 docs/dev/14）或先 stop opik。

App（Expo Go）：
  scripts/kinsun.sh start app      啟動（預設 tunnel，對外可連、不必同網段）
  scripts/kinsun.sh restart app    重啟（改了原生設定或 tunnel 斷線時）
  scripts/kinsun.sh stop app       停止
  scripts/kinsun.sh status         看 app 那列的 exp:// 位址——手機用 Expo Go 掃它
                                   （iOS 用相機、Android 用 Expo Go 內建掃碼）

環境變數：
  KINSUN_RELOAD=1        Webhook 啟用 --reload（開發用；預設關）
  KINSUN_EXPO_TUNNEL=0   App 改走區網（僅手機與 DGX 同一個 Wi-Fi 時可用；啟動較快）
                         預設 1＝tunnel：經 exp.direct 對外，任何網路的手機都連得到。

log：logs/<service>.log　PID：.run/<service>.pid
EOF
}

# ── 進入點 ────────────────────────────────────────────────────────────
case "${1:-}" in
  start)   cmd_start "${2:-}" ;;
  stop)    cmd_stop "${2:-}" ;;
  status)  cmd_status ;;
  restart) cmd_restart "${2:-}" ;;
  ""|-h|--help|help) usage ;;
  *) err "未知指令：$1"; echo; usage; exit 2 ;;
esac
