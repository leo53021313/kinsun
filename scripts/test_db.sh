#!/usr/bin/env bash
#
# test_db.sh — 本機整合測試庫（拋棄式 Postgres＋pgvector）啟停腳本
#
#   scripts/test_db.sh up       啟動測試庫（冪等；已在跑則直接沿用）
#   scripts/test_db.sh down     停止並移除容器（資料一併丟棄）
#   scripts/test_db.sh status   檢視狀態
#   scripts/test_db.sh reset    砍掉重建（清空所有測試資料）
#
# 為什麼要常駐：整合測試（含 ensure_schema 的既有庫升級測試）非連真庫不可，
# 沒有測試庫時會整批 skip——庚-07 的遷移順序缺陷就是這樣靜默溜到正式庫上炸掉的。
# .env 已設 KINSUN_IT=1 與 KINSUN_TEST_DATABASE_URL，容器起著就會自動跑；
# 沒起著則整合測試直接紅並提示跑本腳本（刻意不 skip）。
#
# 與 CI 同一組設定（見 .github/workflows/ci.yml 的 integration job）：
# 同一個 image、同一個 port、同一組帳密——本機綠、CI 才會綠。
#
# ⚠️ 這是拋棄式測試庫，與正式庫（DATABASE_URL）完全無關；conftest 另有防呆，
#    KINSUN_TEST_DATABASE_URL 與 DATABASE_URL 相同時會直接中止（✅ D-69）。

set -o pipefail

CONTAINER="kinsun-test-pg"
IMAGE="pgvector/pgvector:pg17"   # RAG 的 DDL 需要 vector extension，純 postgres 映像會失敗
PORT=5433
PASSWORD="kinsun-test"

if [ -t 1 ]; then
  C_INFO=$'\033[36m'; C_OK=$'\033[32m'; C_ERR=$'\033[31m'; C_OFF=$'\033[0m'
else
  C_INFO=""; C_OK=""; C_ERR=""; C_OFF=""
fi
info() { printf '%s[test-db]%s %s\n' "$C_INFO" "$C_OFF" "$*"; }
ok()   { printf '%s[  ok  ]%s %s\n' "$C_OK"   "$C_OFF" "$*"; }
err()  { printf '%s[ err  ]%s %s\n' "$C_ERR"  "$C_OFF" "$*" >&2; }

command -v docker >/dev/null 2>&1 || { err "找不到 docker，本腳本依賴 Docker 起測試庫。"; exit 1; }

_exists()  { docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; }
_running() { docker ps    --format '{{.Names}}' | grep -qx "$CONTAINER"; }

# 等待 Postgres 真的可接受連線（容器 running ≠ 可連）。
_wait_ready() {
  local i
  for i in $(seq 1 60); do
    docker exec "$CONTAINER" pg_isready -U postgres >/dev/null 2>&1 && return 0
    sleep 1
  done
  return 1
}

cmd_up() {
  if _running; then
    ok "測試庫已在執行（port $PORT）"
    return 0
  fi
  if _exists; then
    info "沿用既有容器，重新啟動…"
    docker start "$CONTAINER" >/dev/null || { err "容器啟動失敗"; exit 1; }
  else
    info "建立測試庫容器（$IMAGE，port $PORT）…"
    # --restart unless-stopped：重開機後自動回來，不必每次手動起。
    docker run -d --name "$CONTAINER" --restart unless-stopped \
      -e POSTGRES_PASSWORD="$PASSWORD" -p "$PORT":5432 "$IMAGE" >/dev/null \
      || { err "容器建立失敗"; exit 1; }
  fi
  info "等待 Postgres 就緒…"
  if _wait_ready; then
    ok "測試庫就緒 → postgresql://postgres:***@localhost:$PORT/postgres"
    info "直接跑：uv run pytest（.env 已設 KINSUN_IT=1，整合測試會自動連這個庫）"
  else
    err "等待逾時，Postgres 未就緒。查看：docker logs $CONTAINER"
    exit 1
  fi
}

cmd_down() {
  if ! _exists; then
    info "測試庫容器不存在，無須停止。"
    return 0
  fi
  info "停止並移除測試庫（資料一併丟棄）…"
  docker rm -f "$CONTAINER" >/dev/null 2>&1
  ok "已移除。整合測試在下次執行時會失敗並提示重跑 scripts/test_db.sh up。"
}

cmd_status() {
  if _running; then
    if docker exec "$CONTAINER" pg_isready -U postgres >/dev/null 2>&1; then
      ok "RUNNING　可連線　port $PORT"
    else
      info "RUNNING　但尚未就緒（啟動中）　port $PORT"
    fi
  elif _exists; then
    err "STOPPED　容器存在但未執行——跑 scripts/test_db.sh up 啟動"
  else
    err "NOT CREATED　尚未建立——跑 scripts/test_db.sh up 建立"
  fi
}

cmd_reset() {
  info "砍掉重建（清空所有測試資料）…"
  docker rm -f "$CONTAINER" >/dev/null 2>&1
  cmd_up
}

usage() {
  cat <<EOF
用法：scripts/test_db.sh <指令>

指令：
  up       啟動本機整合測試庫（冪等；重開機後會自動回來）
  down     停止並移除容器（資料丟棄）
  status   檢視狀態
  reset    砍掉重建（清空測試資料）

設定：$IMAGE　port $PORT　帳號 postgres（與 CI 的 integration job 完全一致）
測試：uv run pytest —— .env 已設 KINSUN_IT=1，整合測試會自動連這個庫
EOF
}

case "${1:-}" in
  up)     cmd_up ;;
  down)   cmd_down ;;
  status) cmd_status ;;
  reset)  cmd_reset ;;
  ""|-h|--help|help) usage ;;
  *) err "未知指令：$1"; echo; usage; exit 2 ;;
esac
