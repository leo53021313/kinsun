"""查詢結果的三道後處理：剔除 → 去重 → 清洗。順序不可調換。

先剔除再去重：座標錯位的那一筆若留到去重階段，可能因為離得近而把正確的那筆擠掉。
先去重再清洗：清洗會把店名截短，截短後不同的店可能看起來一樣。

⚠️ 這三道全部來自 2026-07-27 對真實資料的實測，不是預防性設計。每一條規則的
註解都寫著它擋的是哪一筆真實資料——日後若有人想簡化，請先確認那筆資料已經消失。
"""

from __future__ import annotations

import re

from kinsun.places.geo import distance_meters
from kinsun.places.models import NearbyPlace

# ⚠️ 兩組切點不同，這是刻意的（2026-07-27 實測定案）：
#
# `_SPEAK_CUT` 給 speakable_name 用，要把店名切到「唸得出來的最短形式」，所以連字號
# 與 SEO 符號都算切點——「斗六魷魚羹嘴羹-中和店」唸成「斗六魷魚羹嘴羹」剛好。
# ⚠️ SEO 符號必須是**切點**而不是只把符號刪掉：實測
# 「景安大澤藥局★處方調劑☆藥物保健諮詢★長照2.0諮詢☆…」若只刪符號，整串會連成
# 一氣再被截成 15 字，得到「景安大澤藥局處方調劑藥物保健諮」——比不處理更難聽。
#
# `_STEM_CUT` 給 _stem 用（判斷是不是同一家店），**不含連字號**。連字號在台灣店名裡
# 常用來把描述性前綴接到真正的店名上：實測埔里的「埔里按摩推拿整復-宏益整復所」與
# 「宏益整復所」是同一家，若把連字號當切點，主幹會變成「埔里按摩推拿整復」，
# 與「宏益整復所」互不包含，去重就失效了。
_SPEAK_CUT = re.compile(r"[|｜/／,，、\-—–(（【\[★☆✦✧♡♥※◆◇▲△●○]")
_STEM_CUT = re.compile(r"[|｜/／,，、(（【\[]")
_LINE_ID = re.compile(r"LINE\s*[:：]?\s*@?\w+", re.IGNORECASE)
_SEO_SYMBOLS = re.compile(r"[★☆✦✧♡♥※◆◇▲△●○]")
_SPEAKABLE_MAX_CHARS = 15

# 同址重複的距離門檻。40 公尺是實測值：同一家店的兩筆紀錄相距 2–18 公尺，
# 而同一棟樓的不同店家也在 40 公尺內——故距離只是必要條件，店名主幹才是判準。
_DUPLICATE_METERS = 40

# 行政區指紋的判定門檻。低於此佔比即視為座標可疑。
_SUSPICIOUS_RATIO = 0.02
# 指紋母體小於此數時整道防線停用：樣本太少時「佔比」沒有統計意義。
_MIN_FINGERPRINT_SAMPLE = 50


def speakable_name(name: str) -> str:
    """把店名清成唸得出來的樣子。

    實測 1,418 筆裡 110 筆（7.8%）唸出來會出事，而且集中在離長輩最近的前幾家——
    「景安大澤藥局★處方調劑☆藥物保健諮詢★長照2.0諮詢☆…」整串會被 TTS 唸完。

    與 `agent.py` 的 `_speakable()` 職責不同：那道處理模型自己產出的格式綁架，
    這道處理外部資料帶進來的髒字串。來源不同、規則不同，故不合併。
    """
    cleaned = _LINE_ID.sub("", name)
    cleaned = _SPEAK_CUT.split(cleaned)[0]
    # 切點之前若仍夾雜符號（少見但有），一併清掉。
    cleaned = _SEO_SYMBOLS.sub("", cleaned)
    cleaned = cleaned.strip()
    if len(cleaned) > _SPEAKABLE_MAX_CHARS:
        cleaned = cleaned[:_SPEAKABLE_MAX_CHARS]
    return cleaned


def _stem(name: str) -> str:
    """店名主幹：去掉分隔符之後的內容與空白，用於判斷是不是同一家。

    ⚠️ 用 `_STEM_CUT`（不含連字號）而非 `_SPEAK_CUT`，理由見上面的常數註解。
    """
    return _STEM_CUT.split(_LINE_ID.sub("", name))[0].strip()


def dedupe(found: list[NearbyPlace]) -> list[NearbyPlace]:
    """同一家店被收錄多次時只留最近的一筆。

    ⚠️ 判準是「距離近 **且** 店名主幹互相包含」，不可只用距離。實測中和 1.5 公里內
    餐廳「40 公尺內同類」的配對有 3,684 對，其中店名高度相似者 0 對——那些全是
    同一棟樓或美食街裡的不同店家。只用距離會把整條小吃街刪成一家。
    """
    kept: list[NearbyPlace] = []
    for candidate in sorted(found, key=lambda n: n.distance_meters):
        stem = _stem(candidate.place.name)
        duplicate = False
        for existing in kept:
            near = (
                distance_meters(
                    candidate.place.latitude,
                    candidate.place.longitude,
                    existing.place.latitude,
                    existing.place.longitude,
                )
                <= _DUPLICATE_METERS
            )
            existing_stem = _stem(existing.place.name)
            same = stem in existing_stem or existing_stem in stem
            if near and same:
                duplicate = True
                break
        if not duplicate:
            kept.append(candidate)
    return kept


def drop_suspicious_coordinates(
    found: list[NearbyPlace], fingerprint: list[tuple[str, int]]
) -> list[NearbyPlace]:
    """剔除郵遞區號與鄰域明顯不符者——那代表座標錯置。

    實測案例：`榮總醫院` 座標 (25.1218, 121.4685) 距真正的石牌院區約 5 公里；
    台中西屯 115 公尺處出現「台北推拿大師／北車阿民師」。距離排序抓不到這種錯，
    因為距離就是用錯的座標算出來的。

    ⚠️ 兩個刻意的保守設計：
    1. 沒有郵遞區號的一律保留（已知漏網率約 8.6%）。誤殺合法結果的代價高於放行。
    2. 指紋母體太小時整道防線停用。行政區交界處用「佔比」而非「等於眾數」，
       是為了讓中和／台北交界的合法結果活下來。
    """
    total = sum(count for _, count in fingerprint)
    if total < _MIN_FINGERPRINT_SAMPLE:
        return list(found)
    ratios = {code: count / total for code, count in fingerprint}
    return [
        n
        for n in found
        if not n.place.postcode or ratios.get(n.place.postcode, 0.0) >= _SUSPICIOUS_RATIO
    ]
