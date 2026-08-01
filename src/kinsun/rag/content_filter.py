"""收錄判定：把行政文書與沒有實質內容的空殼擋在衛教 RAG 之外。

2026-08-01 盤點國健署 sitemap 全部 5,667 篇的結果（Leo 核定收錄範圍）：
  ✓ 收錄   2,948 篇  真正能回答長輩健康提問的衛教內容
  ✗ 空殼     877 篇  網頁本身沒內容，東西在 PDF 附件裡
  ✗ 行政     109 篇  預算、招標、法規發布、廉政宣導
  ✗ 步道     150 篇  健走步道與景點導覽——與健康促進有關，但答不了健康問題

判定順序刻意讓「內容」勝過「標題」：先看網頁到底有沒有東西，再談它是什麼。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 行政文書的標題特徵。命中即排除——這些頁面對長輩的健康提問沒有回答價值。
_ADMINISTRATIVE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern)
    for pattern in (
        r"預算|決算|財務報表|會計報告|會計月報|基金來源用途|歲入|歲出",
        r"招標|採購|標案|得標|決標|開標|投標|履約|公開委託|公開徵求|公開評選",
        r"徵才|招募|甄選|人事|職缺|實習|遴選|任免|差勤",
        r"會議紀錄|議事錄|委員會紀錄|座談會紀錄|審查會|國家報告",
        r"出國計畫|考察報告|國外訓練|研習報告",
        r"統計表|統計年報|歷年成果報告|績效報告|評核結果",
        r"施政計畫|施政方針|中程計畫|年度計畫書|管考",
        r"廉政|政風|行政透明|政府資訊公開|檔案應用|資通安全|反貪腐|反賄選",
        r"季報|月報|彙總表|補\(捐\)助|捐助情形|執行政策宣導情形",
        r"得獎名單|通過名單|獲選名單|機構名單|合約.{0,4}名單",
        # 法規／公告的發布本身：標題以這些動詞開頭者一律是行政流程文件
        r"^(公告|預告|發布|修正發布|頒布|訂定|廢止)",
    )
)

# 非內文行：附件清單（檔名、日期、大小）與整行只有一個網址的連結頁。
# 整篇只剩這些代表網頁本身沒有可回答的內容，東西在附件或站外。
_NON_CONTENT_LINE = re.compile(
    r"^(附件|\d{4}-\d{2}-\d{2}|[\d.]+\s*[KM]B"
    r"|\S+\.(?:pdf|odp|ods|docx?|xlsx?|pptx?)"
    r"|https?://\S+)$",
    re.IGNORECASE,
)
# 外站樣板：sitemap 裡混有指向 YouTube 的網址，抓回來的是對方的頁尾。
_EXTERNAL_TEMPLATE = re.compile(r"YouTube 運作方式|© \d{4} Google LLC")
# 健走步道／景點導覽頁的固定欄位。要命中兩個以上才算，避免誤傷只是提到公園的衛教文。
_TRAIL_FIELDS = (
    "健走範圍",
    "健走公里數",
    "環境特色",
    "交通方式",
    "自行開車",
    "大眾運輸",
    "數位實景照片",
)
_NON_WORD = re.compile(r"[^\w]")
_ASCII_ONLY = re.compile(r"^[\x00-\x7F]+$")

# 內容長度下限。刻意訂得很低：「保健闢謠」整篇常常只有 100 字上下就把事情講完，
# 那是全庫最貼近長輩提問的內容。2026-08-01 一度用 150 字為門檻，會砍掉 557 篇。
_MIN_CONTENT_LENGTH = 40
# 內文扣掉標題後所剩不到這個字數，視為只是把標題再讀一次。
_MIN_INFORMATION_BEYOND_TITLE = 30
# 只有短內文才可能是標題複讀；長文直接放行，不做昂貴的字元替換。
_TITLE_ECHO_MAX_LENGTH = 400


@dataclass(frozen=True)
class AdmissionVerdict:
    """收錄與否，以及被擋下來的原因（收錄時為空字串）。"""

    is_admitted: bool
    reason: str = ""


def judge_admission(*, title: str, content: str) -> AdmissionVerdict:
    """判斷一篇文章是否該收進衛教 RAG。

    `content` 應為已剝除網頁樣板的內文（見 `text_cleaner.strip_page_furniture`）。
    """
    body = _without_non_content_lines(content)
    if _is_shell(body, title):
        return AdmissionVerdict(is_admitted=False, reason="空殼")
    if _ASCII_ONLY.match(title.strip()):
        return AdmissionVerdict(is_admitted=False, reason="英文稿")
    if _is_trail_guide(body):
        return AdmissionVerdict(is_admitted=False, reason="步道導覽")
    if any(pattern.search(title) for pattern in _ADMINISTRATIVE_PATTERNS):
        return AdmissionVerdict(is_admitted=False, reason="行政文書")
    return AdmissionVerdict(is_admitted=True)


def _without_non_content_lines(content: str) -> str:
    return "\n".join(
        line
        for raw_line in content.splitlines()
        if (line := raw_line.strip()) and not _NON_CONTENT_LINE.match(line)
    )


def _is_shell(body: str, title: str) -> bool:
    if _EXTERNAL_TEMPLATE.search(body):
        return True
    if len(body) < _MIN_CONTENT_LENGTH:
        return True
    return _is_title_echo(body, title)


def _is_title_echo(body: str, title: str) -> bool:
    if len(body) > _TITLE_ECHO_MAX_LENGTH:
        return False
    stripped = _NON_WORD.sub("", body)
    if not stripped:
        return True
    remainder = stripped.replace(_NON_WORD.sub("", title), "")
    return len(remainder) < _MIN_INFORMATION_BEYOND_TITLE


def _is_trail_guide(body: str) -> bool:
    return sum(1 for field in _TRAIL_FIELDS if field in body) >= 2
