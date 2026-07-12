#!/usr/bin/env bash
#
# backup_db.sh — 資料庫一鍵手動備份（輕量版，✅ D-63 修訂 2026-07-09）
#
#   scripts/backup_db.sh          備份到 data/backups/kinsun_<時間戳>.dump
#
# 時機約定（不做排程）：
#   1. 資料庫結構大改之前（例如乙批 API 大改版動 migration 前）
#   2. 長輩實測開始之前（庫裡即將出現真人健康資料）
#
# 工具說明：DGX 本機未安裝 pg_dump，且 Supabase 伺服器為 PostgreSQL 17
# （pg_dump 版本必須 ≥ 伺服器版本），故以 Docker 官方 postgres:17 映像執行，
# 不需 sudo、不需安裝系統套件。
#
# 還原方式（災難時）：
#   docker run --rm -v "$PWD/data/backups:/backup" -e DATABASE_URL="<新庫連線串>" \
#     postgres:17-alpine sh -c 'pg_restore --dbname="$DATABASE_URL" --no-owner --no-privileges /backup/<檔名>.dump'

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP_DIR="$ROOT/data/backups"
IMAGE="postgres:17-alpine"

# ── 前置檢查 ──────────────────────────────────────────────────────────
command -v docker >/dev/null 2>&1 || { echo "錯誤：找不到 docker，本腳本依賴 Docker 執行 pg_dump。" >&2; exit 1; }

# DATABASE_URL：優先取現有環境變數，否則從 .env 讀取
if [[ -z "${DATABASE_URL:-}" ]]; then
  if [[ -f "$ROOT/.env" ]]; then
    DATABASE_URL="$(grep -E '^DATABASE_URL=' "$ROOT/.env" | tail -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
  fi
fi
[[ -n "${DATABASE_URL:-}" ]] || { echo "錯誤：找不到 DATABASE_URL（環境變數或 .env 皆無）。" >&2; exit 1; }

mkdir -p "$BACKUP_DIR"

STAMP="$(date +%Y%m%d_%H%M%S)"
OUT_NAME="kinsun_${STAMP}.dump"

echo "▶ 開始備份 → data/backups/${OUT_NAME}"

# ── 執行 pg_dump（自訂格式：壓縮、可用 pg_restore 選擇性還原）────────────
# 連線串以環境變數傳入容器、於容器內展開，避免出現在主機指令列。
docker run --rm \
  -v "$BACKUP_DIR:/backup" \
  -e DATABASE_URL="$DATABASE_URL" \
  "$IMAGE" \
  sh -c 'pg_dump --dbname="$DATABASE_URL" --format=custom --no-owner --no-privileges --file="/backup/'"$OUT_NAME"'"'

# ── 驗證：dump 內容可被 pg_restore 讀取（不動任何資料庫）────────────────
OBJECT_COUNT="$(docker run --rm -v "$BACKUP_DIR:/backup" "$IMAGE" \
  sh -c 'pg_restore --list "/backup/'"$OUT_NAME"'"' | grep -c '^[0-9]')"

chmod 600 "$BACKUP_DIR/$OUT_NAME"   # 內含個資，僅限本人讀取

SIZE="$(du -h "$BACKUP_DIR/$OUT_NAME" | cut -f1)"
echo "✔ 備份完成：data/backups/${OUT_NAME}（${SIZE}，${OBJECT_COUNT} 個資料庫物件）"
echo
echo "現有備份："
ls -lht "$BACKUP_DIR" | tail -n +2 | awk '{print "  " $9 "  (" $5 ", " $6 " " $7 " " $8 ")"}'
