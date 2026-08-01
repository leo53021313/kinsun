"""衛教文件文字清理。"""

from __future__ import annotations

import re

_SPACE_RE = re.compile(r"[ \t\r\f\v]+")
_LINE_RE = re.compile(r"\n{3,}")
# \u9ede\u95b1\u8a08\u6578\u6574\u884c\uff08label\uff0b\u7d14\u6578\u5b57\uff09\uff1a\u6bcf\u6b21
# \u8acb\u6c42\u905e\u589e\uff0c\u7559\u8457\u6703\u8b93\u540c\u4e00\u9801\u7684\u5167\u5bb9\u96dc
# \u6e4a
# \u6bcf\u8f2a\u90fd\u4e0d\u540c\u3001\u5168\u91cf\u91cd\u5d4c\uff082026-07-27 \u5be6\u6e2c
#  hpa Detail \u9801\uff09\uff1b\u9650\u6574\u884c\u624d\u6bba\uff0c\u4e0d\u8aa4\u50b7\u5167\u6587
# \u53e5\u5b50\u3002
_VIEW_COUNTER_RE = re.compile(
    r"^(?:\u9ede\u95b1|\u700f\u89bd|\u89c0\u770b)(?:\u6b21\u6578|\u4eba\u6b21|\u7387)\s*[:\uff1a]?\s*[\d,\uff0c]+\s*$"
)


# 文末樣板的起點：相關文章、上下篇、滿意度調查。這之後全部不要。
# 「您可能會喜歡」底下是其他文章的標題，留著會把 A 文章的向量污染成 B。
_TAIL_MARKERS = ("您可能會喜歡", "上一則", "看完本篇主題後", "回上頁", "回首頁")
# 整行完全等於這些字串就丟棄（導覽、分享列、頁尾）。
_FURNITURE_LINES = frozenset(
    {
        "跳到主要內容區塊",
        ":::",
        "定位點",
        "收闔",
        "首頁",
        ">",
        "facebook",
        "line",
        "twitter",
        "plurk",
        "轉寄",
        "列印",
        "縮短網址",
        "分享至",
        "友善列印",
        "回上頁",
        "回首頁",
        "下一則",
        "上一則",
    }
)
# 整行以這些字串開頭就丟棄（後面接單位名或日期）。
_FURNITURE_PREFIXES = ("發布單位：", "更新日期：", "發布日期：", "點閱次數：", "瀏覽次數：")


def strip_page_furniture(text: str, *, title: str) -> str:
    """剝掉網頁樣板（站台選單、麵包屑、分享列、發布資訊、文末相關文章）。

    政府網站多半不用語意標籤（hpa 的分類選單就是普通 div），HTML 解析器的
    nav／header／footer 規則攔不到，只能在文字層處理。2026-08-01 實測 150 篇
    hpa 文章：剝除前平均 953 字且 100% 含導覽字樣，剝除後平均 312 字、雜訊歸零。

    刻意不設長度下限——「保健闢謠」整篇常常只有 100 字就把事情講完，那是全庫
    最貼近長輩提問的內容，用長度過濾會一口氣砍掉 557 篇。
    """
    lines = [line.strip() for line in text.splitlines()]

    # 一、截掉文末樣板。限定在後段才判定，避免正文引用到同樣的詞。
    tail = len(lines)
    for index, line in enumerate(lines):
        if index > len(lines) * 0.3 and line.startswith(_TAIL_MARKERS):
            tail = min(tail, index)
    lines = lines[:tail]

    # 二、截掉文首導覽。麵包屑的特徵是「首頁 > A > B > 分類名」，最後一個 ">"
    #     的下一行就是分類名，連它一起丟。用「前面要有『首頁』」判定而非位置比例：
    #     短文件裡正文的 ">" 也會落在前 60%，位置判斷會把正文整段吃掉。
    arrows = [index for index, line in enumerate(lines) if line == ">"]
    if arrows and any(line == "首頁" for line in lines[: arrows[-1]]):
        lines = lines[arrows[-1] + 2 :]

    # 三、逐行過濾剩餘樣板，並移除與標題重複的那一行。
    kept = [
        line
        for line in lines
        if line
        and line not in _FURNITURE_LINES
        and not line.startswith(_FURNITURE_PREFIXES)
        and line != title
        and not (line.endswith(title) and line.count(title) == 1 and len(line) - len(title) <= 20)
    ]
    return "\n".join(kept)


def clean_text(text: str) -> str:
    cleaned = text.replace("\x00", "")  # Postgres text \u6b04\u4f4d\u4e0d\u63a5\u53d7 NUL
    cleaned = cleaned.replace("\u3000", " ")
    cleaned = _SPACE_RE.sub(" ", cleaned)
    lines = [line.strip() for line in cleaned.splitlines()]
    cleaned = "\n".join(line for line in lines if not _VIEW_COUNTER_RE.match(line))
    cleaned = _LINE_RE.sub("\n\n", cleaned)
    return cleaned.strip()
