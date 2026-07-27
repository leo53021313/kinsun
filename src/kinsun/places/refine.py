"""查詢結果的三道後處理：剔除 → 去重 → 清洗。順序不可調換。

先剔除再去重：座標錯位的那一筆若留到去重階段，可能因為離得近而把正確的那筆擠掉。
先去重再清洗：清洗會把店名截短，截短後不同的店可能看起來一樣。

⚠️ 這三道全部來自 2026-07-27 對真實資料的實測，不是預防性設計。每一條規則的
註解都寫著它擋的是哪一筆真實資料——日後若有人想簡化，請先確認那筆資料已經消失。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

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
# ⚠️ 連字號只在「不夾在英數字之間」時才算切點（2026-07-27 實測）：全台有 13,341 筆
# 店名的英數字之間帶連字號，其中 1,340 筆是 7-ELEVEN／7-11 開頭——無條件切會讓
# 「7-ELEVEN 石潭門市」變成「7」，而超商是 categories.py 明訂的分類、密度全台最高，
# 長輩問一次附近超商就必然踩到。「斗六魷魚羹嘴羹-中和店」這種中文接連字號仍會被切。
_SPEAK_CUT = re.compile(
    r"[|｜/／,，、(（【\[★☆✦✧♡♥※◆◇▲△●○]|(?<![0-9A-Za-z])[-—–]|[-—–](?![0-9A-Za-z])"
)
_STEM_CUT = re.compile(r"[|｜/／,，、(（【\[]")
_LINE_ID = re.compile(r"LINE\s*[:：]?\s*@?\w+", re.IGNORECASE)
_SEO_SYMBOLS = re.compile(r"[★☆✦✧♡♥※◆◇▲△●○]")
_SPEAKABLE_MAX_CHARS = 15

# 同址重複的距離門檻。40 公尺是實測值：同一家店的兩筆紀錄相距 2–18 公尺，
# 而同一棟樓的不同店家也在 40 公尺內——故距離只是必要條件，店名主幹才是判準。
_DUPLICATE_METERS = 40

# 店名主幹要有這麼長，「互相包含」才算得數（2026-07-27 實測）。全台有 7,412 筆
# 店名剛好兩個字，其中就有「全家」——沒有長度門檻時，「全家」會被判定為
# 「全家福小吃店」的重複而讓其中一家消失。取 4：實測要對上的
# 「宏益整復所」是 5 字，過得了；「全家」「小高」這種 2 字則過不了。
_MIN_STEM_FOR_CONTAINMENT = 4

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
    stripped = _LINE_ID.sub("", name)
    cleaned = _SEO_SYMBOLS.sub("", _SPEAK_CUT.split(stripped)[0]).strip()
    if not cleaned:
        # 名字以分隔符開頭時第一段是空的（實測全台 705 筆）。回空字串等於把這家店
        # 從長輩的答案裡抹掉，比唸得不漂亮更糟——退回「整串去掉分隔符與符號」。
        cleaned = _SEO_SYMBOLS.sub("", _SPEAK_CUT.sub("", stripped)).strip()
    if len(cleaned) > _SPEAKABLE_MAX_CHARS:
        cleaned = cleaned[:_SPEAKABLE_MAX_CHARS]
    return cleaned


def _stem(name: str) -> str:
    """店名主幹：去掉分隔符之後的內容與空白，用於判斷是不是同一家。

    ⚠️ 用 `_STEM_CUT`（不含連字號）而非 `_SPEAK_CUT`，理由見上面的常數註解。

    ⚠️ 切出空字串時退回「整個名字去掉分隔符」（2026-07-27 實測）：全台有 705 筆店名
    以分隔符開頭（「【麵匠】麵食堂-彌陀總店」「(預約制)喜嫁六禮十二禮」）。空字串是
    **任何字串的子字串**，若讓它進到 `dedupe` 的包含判斷，那一筆會變成萬用比對，
    把四十公尺內所有不相干的合法店家全部當成重複刪掉——長輩問附近有什麼藥局會
    只剩下那家名字格式異常的。
    """
    cleaned = _LINE_ID.sub("", name)
    head = _STEM_CUT.split(cleaned)[0].strip()
    return head or _STEM_CUT.sub("", cleaned).strip()


def _same_shop(stem: str, other: str) -> bool:
    """兩個店名主幹是不是同一家。

    ⚠️ 「互相包含」必須加最短長度門檻，否則短店名會吃掉不相干的店：實測全台有
    7,412 筆店名剛好兩個字（含「全家」），沒有門檻時「全家」會被判定為
    「全家福小吃店」的重複。完全相同則不受門檻限制——那本來就是同一個名字。
    """
    if not stem or not other:
        return False
    if stem == other:
        return True
    shorter = min(len(stem), len(other))
    if shorter < _MIN_STEM_FOR_CONTAINMENT:
        return False
    return stem in other or other in stem


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
            if near and _same_shop(stem, existing_stem):
                duplicate = True
                break
        if not duplicate:
            kept.append(candidate)
    return kept


@dataclass(frozen=True)
class SpokenPlace:
    """三道處理跑完、可以直接唸給長輩聽的一筆。"""

    name: str
    distance_meters: int
    phone: str | None


def refine(
    found: list[NearbyPlace], fingerprint: list[tuple[str, int]], *, limit: int
) -> list[SpokenPlace]:
    """三道處理的唯一入口：剔除 → 去重 → 清洗，順序寫死在這裡。

    ⚠️ 為什麼要有這個函式，而不是讓呼叫端自己依序呼叫三支（2026-07-27 審查發現）：
    「順序不可調換」原本只寫在檔頭註解裡，而註解管不住呼叫端。實測顛倒順序的後果——
    座標錯置的那筆因為看起來比較近而被 `dedupe` 留下、正確的那筆被當成重複丟掉，
    接著它自己又被 `drop_suspicious_coordinates` 剔除，**長輩最後什麼都聽不到**。
    把順序關進單一入口，呼叫端就沒有機會弄錯。

    截斷放在最後：先處理完才取前幾筆，否則被剔除或去重掉的會白白佔掉名額。
    """
    kept = dedupe(drop_suspicious_coordinates(found, fingerprint))
    spoken = []
    for item in kept:
        name = speakable_name(item.place.name)
        if not name:
            continue
        spoken.append(SpokenPlace(name, item.distance_meters, item.place.phone))
        if len(spoken) >= limit:
            break
    return spoken


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
