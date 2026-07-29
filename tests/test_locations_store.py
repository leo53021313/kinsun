"""座標有效性判準（V-04，2026-07-29）。

這條規則有兩個呼叫端（`channels/app/ws.py` 的 JSON 訊框、`channels/app/turns.py`
的 query 參數），故住在領域層當單一出處——兩邊各寫一份正是 2026-07-28 位置鍵名
不合那個故障的成因（兩邊單元測試各自斷言自己那一版契約，所以全綠）。
"""

from __future__ import annotations

import math

import pytest

from kinsun.locations.store import is_valid_coordinate, is_valid_place


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


# ── 地名長度上限（V-05，2026-07-29）──────────────────────────────────────


@pytest.mark.parametrize(
    ("place", "why"),
    [
        ("台南市", "一般縣市"),
        ("東區", "行政區"),
        ("Kaohsiung City", "英文地名"),
        ("台" * 100, "剛好在上限"),
    ],
)
def test_real_place_names_are_accepted(place, why):
    assert is_valid_place(place), why


@pytest.mark.parametrize(
    ("place", "why"),
    [
        ("台" * 101, "超過上限一個字"),
        ("x" * 20000, "實測抓到的 2 萬字"),
        ("", "空字串＝這輪沒有位置，不寫入"),
        ("   ", "只有空白"),
        (None, "型別不對"),
        (123, "型別不對"),
        (["台南市"], "型別不對"),
    ],
)
def test_bad_place_names_are_rejected(place, why):
    assert not is_valid_place(place), why


def test_length_is_measured_after_trimming():
    """前後空白不算長度——與座標判準同樣的取捨：寧可寬鬆也不要誤殺真實地名。"""
    assert is_valid_place("  台南市  ")


def test_the_limit_is_generous_on_purpose():
    """⚠️ 這個上限刻意訂得寬。

    地名被拒的失敗模式是**靜默的**（伺服器端忽略、不回錯），長輩那端的表現是金孫又
    開始反問「您人在哪裡」——那正是 2026-07-28 那次故障的症狀，而且後台查不出原因。
    App 送的是 `address.city ?? subregion ?? region`，全是短的行政區名，100 字遠遠夠用；
    訂這個界線是為了擋掉 2 萬字灌進每一輪提示詞，不是為了規範格式。
    """
    assert is_valid_place("台北市內湖區")
    assert is_valid_place("Kaohsiung City, Taiwan")
