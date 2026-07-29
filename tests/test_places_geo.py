"""Haversine 距離：Fake 與 Pg 兩個 adapter 的距離必須算得一樣，故抽成共用純函式。"""

from __future__ import annotations

from kinsun.places.geo import bounding_box, distance_meters


def test_distance_between_identical_points_is_zero():
    assert distance_meters(25.0, 121.5, 25.0, 121.5) == 0


def test_distance_matches_known_pair():
    # 長輩家 (25.0, 121.5) → 小高拉麵連城店 (25.00169, 121.49776)，實測約 294 公尺。
    assert 285 <= distance_meters(25.0, 121.5, 25.00169, 121.49776) <= 305


def test_bounding_box_covers_the_radius():
    lat_lo, lat_hi, lon_lo, lon_hi = bounding_box(25.0, 121.5, 1500)
    # 正north 1500 公尺的點必須落在框內（緯度每度約 111,320 公尺）。
    assert lat_lo < 25.0 - 1500 / 111320 * 0.99
    assert lat_hi > 25.0 + 1500 / 111320 * 0.99
    # 經度在此緯度會被 cos 放大，框必須比緯度那一邊寬。
    assert (lon_hi - lon_lo) > (lat_hi - lat_lo)
