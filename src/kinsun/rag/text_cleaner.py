"""衛教文件文字清理。"""

from __future__ import annotations

import re

_SPACE_RE = re.compile(r"[ \t\r\f\v]+")
_LINE_RE = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    cleaned = text.replace("\x00", "")  # Postgres text \u6b04\u4f4d\u4e0d\u63a5\u53d7 NUL
    cleaned = cleaned.replace("\u3000", " ")
    cleaned = _SPACE_RE.sub(" ", cleaned)
    cleaned = "\n".join(line.strip() for line in cleaned.splitlines())
    cleaned = _LINE_RE.sub("\n\n", cleaned)
    return cleaned.strip()
