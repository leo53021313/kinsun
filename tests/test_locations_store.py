"""座標有效性判準（V-04，2026-07-29）。

這條規則有兩個呼叫端（`channels/app/ws.py` 的 JSON 訊框、`channels/app/turns.py`
的 query 參數），故住在領域層當單一出處——兩邊各寫一份正是 2026-07-28 位置鍵名
不合那個故障的成因（兩邊單元測試各自斷言自己那一版契約，所以全綠）。
"""

from __future__ import annotations

import math

import pytest

from kinsun.locations.store import is_valid_coordinate


@pytest.mark.parametrize(
    ("lat", "lon"),
    [
        (22.99, 120.21),  # 台南
        (25.03, 121.56),  # 台北
        (0, 0),  # 幾內亞灣外海：荒謬但合法，判準不該替業務決定「這裡不可能有人」
        (90.0, 180.0),  # 邊界值屬合法
        (-90.0, -180.0),
    ],
)
def test_real_coordinates_are_accepted(lat, lon):
    assert is_valid_coordinate(lat, lon)


@pytest.mark.parametrize(
    ("lat", "lon", "why"),
    [
        (999, 120.21, "緯度超出 ±90"),
        (-999, 120.21, "緯度超出 -90"),
        (22.99, 999, "經度超出 ±180"),
        (22.99, -999, "經度超出 -180"),
        (90.1, 120.21, "剛好越界"),
        (22.99, 180.1, "剛好越界"),
    ],
)
def test_out_of_range_coordinates_are_rejected(lat, lon, why):
    assert not is_valid_coordinate(lat, lon), why


@pytest.mark.parametrize(
    ("lat", "lon", "why"),
    [
        (None, 120.21, "缺緯度"),
        (22.99, None, "缺經度"),
        (None, None, "兩者皆缺"),
        ("22.99", 120.21, "字串"),
        ([22.99], 120.21, "陣列"),
        ({"n": 1}, 120.21, "物件"),
    ],
)
def test_non_numeric_coordinates_are_rejected(lat, lon, why):
    assert not is_valid_coordinate(lat, lon), why


def test_booleans_are_rejected_rather_than_coerced():
    """⚠️ bool 是 int 的子型別，`float(True)` 是 1.0——會把長輩安靜地記在外海。

    這不是假想：WS 訊框實測傳 `{"latitude": true}` 不會報錯，會寫進一筆看起來
    完全正常的位置。故必須單獨排除，不能只寫 isinstance(x, (int, float))。
    """
    assert not is_valid_coordinate(True, 120.21)
    assert not is_valid_coordinate(22.99, False)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_nan_and_infinity_are_rejected(bad):
    """`json.loads` 接受 `NaN`／`Infinity` 字面值（非標準 JSON 但 Python 預設允許），
    所以這兩個真的進得來。NaN 的比較恆為 False，範圍判斷剛好擋住，但必須有測試釘死
    ——換成 `abs(lat) > 90` 這種寫法就會漏掉 NaN。"""
    assert not is_valid_coordinate(bad, 120.21)
    assert not is_valid_coordinate(22.99, bad)
