"""Overture Maps 台灣 POI → places 表。每月手動跑一次。

    uv run --with duckdb python -m kinsun.places.ingest

⚠️ DuckDB 走 `uv run --with` 而不進專案相依：它只在這支每月手動跑一次的 CLI 用得到，
為此讓 webhook 與 scheduler 也扛一個大套件並不划算（AGENTS.md：除非有充分理由，
否則不要新增第三方套件）。

⚠️ 不做自動排程：資料一個月才變一次，養一個定時任務不划算，而且跑壞了沒人看得到。

⚠️ 2026-09 前必須複驗：Overture 的 `categories` 欄位已標記 deprecated 並將於
2026-09 release 移除。本腳本改用 `taxonomy.primary` 取代它——2026-07-27 以
release 2026-07-22.0 實測確認：`taxonomy.primary` 與舊 `categories.primary`
對絕大多數類別給出相同筆數（如 restaurant、pharmacy、hair_salon），但兩者
**不是簡單改名**：
  - `food_truck_stand`／`ramen_restaurant` 這兩個 `categories.py` 用到的值，
    在舊 `categories.primary` 底下完全不存在（0 筆），只存在於新的
    `taxonomy.primary`——代表 `categories.py` 原本就是照新欄位的粒度校準的。
  - `dentist` 在新欄位下已重新命名為 `dental_clinic`；`buddhist_temple` 重新
    命名為 `buddhist_place_of_worship`；`doctor`（舊欄位 1,006 筆）在新欄位下
    完全沒有對應值（新欄位為 NULL）。這三類目前仍用舊值比對，實際上退化成
    完全依賴中文店名關鍵字比對（`categories.py` 的 exclude／keywords 機制本來
    就是主防線，見該檔案開頭說明），本次驗證未觀察到功能性缺口，但下次改版
    複驗時應一併確認這幾個值是否有更新。
  - `basic_category` 是更粗的分類（全庫僅 243 種值），會讓 hair_salon／barber
    這類已校準的細分類全部併入 `personal_or_beauty_service`，故不採用。
"""

from __future__ import annotations

import argparse
import logging
import os
import time

from kinsun.db import Database
from kinsun.places.categories import CATEGORIES, matches
from kinsun.places.models import Place
from kinsun.places.store import PgPlaceStore

logger = logging.getLogger("kinsun.places.ingest")

_RELEASE = "2026-07-22.0"
_S3 = "s3://overturemaps-us-west-2/release/{release}/theme=places/type=place/*"

# ⚠️ bbox 必須含金門馬祖：lon 118.1 起（金門在 118.3），lat 26.4 止（馬祖在 26.2）。
# 只取 119.3–122.1／21.8–25.4 會把外島整個漏掉。
_BBOX = {"lon_lo": 118.1, "lon_hi": 122.1, "lat_lo": 21.8, "lat_hi": 26.4}

_BATCH = 500


def _fetch_rows(release: str) -> list[tuple]:
    import duckdb  # 延遲匯入：只有這支 CLI 需要，匯入本模組的其他人不該被迫安裝

    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';")
    return con.execute(
        f"""
        SELECT id,
               names.primary                          AS name,
               bbox.xmin                              AS lon,
               bbox.ymin                              AS lat,
               taxonomy.primary                       AS overture_category,
               confidence,
               addresses[1].freeform                  AS address,
               left(addresses[1].postcode, 3)         AS postcode,
               addresses[1].locality                  AS city,
               phones[1]                              AS phone
        FROM read_parquet('{_S3.format(release=release)}', filename=true, hive_partitioning=1)
        WHERE bbox.xmin BETWEEN {_BBOX["lon_lo"]} AND {_BBOX["lon_hi"]}
          AND bbox.ymin BETWEEN {_BBOX["lat_lo"]} AND {_BBOX["lat_hi"]}
          AND names.primary IS NOT NULL
        """
    ).fetchall()


def _classify(name: str, overture_category: str | None) -> list[str]:
    """一家店可能同時屬於多類（拉麵店既是 restaurant 也是 noodles），故回傳清單。"""
    return [code for code in CATEGORIES if matches(code, name, overture_category=overture_category)]


def main() -> None:
    parser = argparse.ArgumentParser(description="把 Overture 台灣 POI 灌進 places 表")
    parser.add_argument("--release", default=_RELEASE, help=f"Overture release，預設 {_RELEASE}")
    parser.add_argument("--dry-run", action="store_true", help="只統計不寫庫")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger.info("開始抽取 Overture release=%s", args.release)
    rows = _fetch_rows(args.release)
    logger.info("台灣範圍內共 %d 筆有店名的 POI", len(rows))

    now = time.time()
    places: list[Place] = []
    for pid, name, lon, lat, ocat, conf, address, postcode, city, phone in rows:
        for code in _classify(name, ocat):
            places.append(
                Place(
                    # 同一家店可能落進多個類別，place_id 必須帶上類別才不會互相覆蓋。
                    place_id=f"{pid}:{code}",
                    name=name,
                    latitude=lat,
                    longitude=lon,
                    category=code,
                    overture_category=ocat,
                    confidence=conf,
                    address=address,
                    postcode=postcode,
                    city=city,
                    phone=phone,
                    ingested_at=now,
                )
            )

    by_category: dict[str, int] = {}
    for place in places:
        by_category[place.category] = by_category.get(place.category, 0) + 1
    for code, count in sorted(by_category.items(), key=lambda kv: -kv[1]):
        logger.info("  %-18s %6d 筆", code, count)
    logger.info("待寫入合計 %d 列", len(places))

    if args.dry_run:
        logger.info("--dry-run，不寫庫")
        return

    # Database.open 是全庫取得連線池的唯一入口（見 db.py 的 keepalive 說明）。
    database = Database.open(os.environ["DATABASE_URL"])
    store = PgPlaceStore(database)
    for start in range(0, len(places), _BATCH):
        store.save_many(places[start : start + _BATCH])
        logger.info("已寫入 %d/%d", min(start + _BATCH, len(places)), len(places))
    logger.info("完成")


if __name__ == "__main__":
    main()
