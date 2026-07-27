"""球面距離與矩形粗篩：Fake 與 Pg 兩個 adapter 共用同一份幾何，避免各算各的。

刻意不引入 PostGIS 或 geopy：候選集經矩形粗篩後只剩數百筆，Haversine 足夠，
而少一個資料庫擴充相依，就少一個「Supabase 有沒有裝」的外部變數。
"""

from __future__ import annotations

import math

_EARTH_RADIUS_METERS = 6371000.0
# 緯度每度的公尺數（全球近似定值）；經度每度會隨緯度被 cos 收窄，故另外算。
_METERS_PER_DEGREE_LAT = 111320.0


def distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    """兩點球面距離（公尺，四捨五入到整數）。"""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return round(_EARTH_RADIUS_METERS * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def bounding_box(lat: float, lon: float, radius_meters: float) -> tuple[float, float, float, float]:
    """回傳 (lat_lo, lat_hi, lon_lo, lon_hi)：能完整覆蓋該半徑的矩形。

    先用矩形把索引吃到（btree 對範圍查詢有效），再用 Haversine 精算——直接對全表
    算三角函數會掃描整張表。矩形一定比圓大，故不會漏，只會多撈一些再被距離濾掉。
    """
    lat_delta = radius_meters / _METERS_PER_DEGREE_LAT
    # 高緯度時 cos 會趨近 0 使框無限寬；台灣在北緯 21–26 度之間，cos 約 0.9，
    # 但仍加下限保護，避免極端輸入產生除以零。
    cos_lat = max(math.cos(math.radians(lat)), 0.01)
    lon_delta = radius_meters / (_METERS_PER_DEGREE_LAT * cos_lat)
    return (lat - lat_delta, lat + lat_delta, lon - lon_delta, lon + lon_delta)
