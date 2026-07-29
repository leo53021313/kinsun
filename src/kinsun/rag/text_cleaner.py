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


def clean_text(text: str) -> str:
    cleaned = text.replace("\x00", "")  # Postgres text \u6b04\u4f4d\u4e0d\u63a5\u53d7 NUL
    cleaned = cleaned.replace("\u3000", " ")
    cleaned = _SPACE_RE.sub(" ", cleaned)
    lines = [line.strip() for line in cleaned.splitlines()]
    cleaned = "\n".join(line for line in lines if not _VIEW_COUNTER_RE.match(line))
    cleaned = _LINE_RE.sub("\n\n", cleaned)
    return cleaned.strip()
