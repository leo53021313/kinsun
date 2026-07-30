"""產生 Kinsun UX 圖表、低保真線框圖、PNG、Contact Sheet 與 manifest。

設計原則：
- 唯一內容來源是 diagrams/source/diagram-spec.json 與
  wireframes/source/wireframe-spec.json。
- 只使用 Python 標準函式庫與 Pillow；不連外、不載入 CDN、不包入字型檔。
- SVG 與 PNG 共用同一組繪圖指令，避免兩種匯出內容不一致。

執行：
    uv run --locked python docs/uiux/tools/generate_assets.py

可用 UIUX_FONT_PATH 指定本機繁中文字型；未指定時會依 Windows、macOS、
Linux 的常見系統字型順序尋找。
"""

from __future__ import annotations

import base64
import html
import io
import json
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[3]
UIUX_ROOT = REPO_ROOT / "docs" / "uiux"
DIAGRAM_SOURCE = UIUX_ROOT / "diagrams" / "source"
DIAGRAM_EXPORT = UIUX_ROOT / "diagrams" / "export"
WIREFRAME_SOURCE = UIUX_ROOT / "wireframes" / "source"
WIREFRAME_EXPORT = UIUX_ROOT / "wireframes" / "export"
CONTACT_SHEETS = UIUX_ROOT / "contact-sheets"
MANIFEST_PATH = UIUX_ROOT / "asset-manifest.json"

SVG_FONT_STACK = "'Microsoft JhengHei','PingFang TC','Noto Sans CJK TC','Noto Sans TC',sans-serif"
PALETTE = {
    "ink": "#202124",
    "muted": "#5F6368",
    "line": "#9AA0A6",
    "soft": "#F1F3F4",
    "surface": "#FFFFFF",
    "accent": "#DADCE0",
    "dark": "#3C4043",
    "danger": "#4A4A4A",
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def repo_relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def find_font_path() -> Path | None:
    configured = os.environ.get("UIUX_FONT_PATH")
    candidates = [
        configured,
        r"C:\Windows\Fonts\msjh.ttc",
        r"C:\Windows\Fonts\msjhbd.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansTC-Regular.ttf",
        "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


FONT_PATH = find_font_path()
_FONT_CACHE: dict[tuple[int, bool], ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    key = (size, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    if FONT_PATH:
        path = FONT_PATH
        if bold and sys.platform.startswith("win"):
            bold_path = Path(r"C:\Windows\Fonts\msjhbd.ttc")
            if bold_path.is_file():
                path = bold_path
        loaded = ImageFont.truetype(str(path), size=size, index=0)
    else:
        loaded = ImageFont.load_default()
    _FONT_CACHE[key] = loaded
    return loaded


def wrap_text(value: str, max_chars: int) -> list[str]:
    """以全形字寬近似換行，保留已存在的換行。"""
    result: list[str] = []
    for paragraph in value.splitlines() or [""]:
        if not paragraph:
            result.append("")
            continue
        current = ""
        width = 0
        for char in paragraph:
            char_width = 1 if ord(char) < 128 else 2
            if current and width + char_width > max_chars * 2:
                result.append(current)
                current = char
                width = char_width
            else:
                current += char
                width += char_width
        if current:
            result.append(current)
    return result


@dataclass
class Canvas:
    width: int
    height: int

    def __post_init__(self) -> None:
        self.image = Image.new("RGB", (self.width, self.height), PALETTE["surface"])
        self.draw = ImageDraw.Draw(self.image)
        self.svg: list[str] = [
            (
                f'<svg xmlns="http://www.w3.org/2000/svg" '
                f'width="{self.width}" height="{self.height}" '
                f'viewBox="0 0 {self.width} {self.height}" role="img">'
            ),
            "<style>"
            f"text{{font-family:{SVG_FONT_STACK};fill:{PALETTE['ink']};}}"
            ".muted{fill:#5F6368}.label{font-weight:700;letter-spacing:.4px}"
            "</style>",
        ]

    def rect(
        self,
        xy: tuple[float, float, float, float],
        *,
        fill: str = PALETTE["surface"],
        outline: str = PALETTE["line"],
        width: int = 2,
        radius: int = 10,
        dash: bool = False,
    ) -> None:
        x1, y1, x2, y2 = xy
        self.draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)
        dash_attr = ' stroke-dasharray="7 5"' if dash else ""
        self.svg.append(
            f'<rect x="{x1}" y="{y1}" width="{x2 - x1}" height="{y2 - y1}" '
            f'rx="{radius}" fill="{fill}" stroke="{outline}" stroke-width="{width}"{dash_attr}/>'
        )

    def line(
        self,
        xy: tuple[float, float, float, float],
        *,
        fill: str = PALETTE["line"],
        width: int = 2,
        arrow: bool = False,
        dash: bool = False,
    ) -> None:
        x1, y1, x2, y2 = xy
        self.draw.line(xy, fill=fill, width=width)
        dash_attr = ' stroke-dasharray="7 5"' if dash else ""
        self.svg.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{fill}" stroke-width="{width}"{dash_attr}/>'
        )
        if arrow:
            if abs(y2 - y1) >= abs(x2 - x1):
                points = [(x2, y2), (x2 - 6, y2 - 10), (x2 + 6, y2 - 10)]
            else:
                points = [(x2, y2), (x2 - 10, y2 - 6), (x2 - 10, y2 + 6)]
            self.draw.polygon(points, fill=fill)
            points_attr = " ".join(f"{x},{y}" for x, y in points)
            self.svg.append(f'<polygon points="{points_attr}" fill="{fill}"/>')

    def circle(
        self,
        center: tuple[float, float],
        radius: float,
        *,
        fill: str = PALETTE["soft"],
        outline: str = PALETTE["dark"],
        width: int = 2,
    ) -> None:
        cx, cy = center
        box = (cx - radius, cy - radius, cx + radius, cy + radius)
        self.draw.ellipse(box, fill=fill, outline=outline, width=width)
        self.svg.append(
            f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="{fill}" '
            f'stroke="{outline}" stroke-width="{width}"/>'
        )

    def text(
        self,
        position: tuple[float, float],
        value: str,
        *,
        size: int = 18,
        fill: str = PALETTE["ink"],
        bold: bool = False,
        anchor: str = "la",
    ) -> None:
        x, y = position
        pil_anchor = {
            "la": "la",
            "ma": "ma",
            "ra": "ra",
            "mm": "mm",
            "lm": "lm",
        }.get(anchor, "la")
        self.draw.text((x, y), value, font=font(size, bold), fill=fill, anchor=pil_anchor)
        svg_anchor = {"ma": "middle", "mm": "middle", "ra": "end"}.get(anchor, "start")
        weight = "700" if bold else "400"
        dominant = ' dominant-baseline="middle"' if anchor in {"mm", "lm"} else ""
        self.svg.append(
            f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{svg_anchor}"{dominant}>'
            f"{html.escape(value)}</text>"
        )

    def text_block(
        self,
        position: tuple[float, float],
        value: str,
        *,
        max_chars: int,
        size: int = 18,
        fill: str = PALETTE["ink"],
        bold: bool = False,
        line_height: int | None = None,
        max_lines: int | None = None,
    ) -> int:
        x, y = position
        lines = wrap_text(value, max_chars)
        if max_lines and len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = lines[-1].rstrip("…") + "…"
        step = line_height or int(size * 1.45)
        for index, line in enumerate(lines):
            self.text((x, y + index * step), line, size=size, fill=fill, bold=bold)
        return max(1, len(lines)) * step

    def save(self, svg_path: Path, png_path: Path) -> None:
        svg_path.parent.mkdir(parents=True, exist_ok=True)
        png_path.parent.mkdir(parents=True, exist_ok=True)
        save_text(svg_path, "\n".join([*self.svg, "</svg>"]))
        self.image.save(png_path, format="PNG", optimize=True)


def split_node(value: str) -> tuple[str, str]:
    if "｜" in value:
        kind, label = value.split("｜", 1)
        return kind.strip(), label.strip()
    return "節點", value.strip()


def render_diagram(entry: dict[str, Any], svg_path: Path, png_path: Path) -> None:
    lanes: list[dict[str, Any]] = entry["lanes"]
    width = 1200
    max_nodes = max(len(lane["items"]) for lane in lanes)
    # 節點從 y=195 開始；每列佔 96，底部另保留圖說與安全留白。
    height = max(680, 260 + max_nodes * 96)
    canvas = Canvas(width, height)
    canvas.text((48, 40), entry["title"], size=30, bold=True)
    canvas.text(
        (48, 78),
        f"{entry['section']}｜{entry.get('evidence', '提案')}｜一圖一問",
        size=15,
        fill=PALETTE["muted"],
    )
    canvas.line((48, 105, width - 48, 105), fill=PALETTE["dark"], width=2)

    gap = 20
    lane_width = (width - 96 - gap * (len(lanes) - 1)) / len(lanes)
    top = 130
    for lane_index, lane in enumerate(lanes):
        x1 = 48 + lane_index * (lane_width + gap)
        x2 = x1 + lane_width
        canvas.rect((x1, top, x2, top + 46), fill=PALETTE["dark"], outline=PALETTE["dark"])
        canvas.text((x1 + 16, top + 13), lane["name"], size=17, fill="#FFFFFF", bold=True)
        node_top = top + 65
        for node_index, raw_node in enumerate(lane["items"]):
            kind, label = split_node(raw_node)
            node_height = 72
            canvas.rect((x1, node_top, x2, node_top + node_height), fill=PALETTE["soft"])
            canvas.text((x1 + 13, node_top + 10), kind, size=12, fill=PALETTE["muted"], bold=True)
            canvas.text_block(
                (x1 + 13, node_top + 31),
                label,
                max_chars=max(8, int(lane_width / 19)),
                size=15,
                max_lines=2,
                line_height=21,
            )
            if node_index < len(lane["items"]) - 1:
                canvas.line(
                    ((x1 + x2) / 2, node_top + node_height, (x1 + x2) / 2, node_top + 91),
                    arrow=True,
                )
            node_top += 96
        if lane_index < len(lanes) - 1:
            next_x = x2 + gap
            canvas.line((x2, top + 23, next_x, top + 23), arrow=True, dash=True)

    canvas.text(
        (width - 48, height - 28),
        "灰階架構圖；短標籤呈現關係，完整規格見對應 Markdown。",
        size=13,
        fill=PALETTE["muted"],
        anchor="ra",
    )
    canvas.save(svg_path, png_path)


def mermaid_source(entry: dict[str, Any]) -> str:
    lines = [
        "---",
        f"title: {entry['title']}",
        "---",
        "flowchart TD",
    ]
    previous_lane_last: str | None = None
    for lane_index, lane in enumerate(entry["lanes"]):
        lane_id = f"L{lane_index}"
        lines.append(f'  subgraph {lane_id}["{lane["name"]}"]')
        previous_node: str | None = None
        for node_index, raw_node in enumerate(lane["items"]):
            node_id = f"{lane_id}N{node_index}"
            kind, label = split_node(raw_node)
            safe_label = f"{kind}：{label}".replace('"', "＂")
            lines.append(f'    {node_id}["{safe_label}"]')
            if previous_node:
                lines.append(f"    {previous_node} --> {node_id}")
            previous_node = node_id
        lines.append("  end")
        if previous_lane_last and lane["items"]:
            lines.append(f"  {previous_lane_last} -.-> {lane_id}N0")
        if lane["items"]:
            previous_lane_last = f"{lane_id}N{len(lane['items']) - 1}"
    return "\n".join(lines) + "\n"


def block_parts(raw: str) -> tuple[str, list[str]]:
    parts = raw.split("|")
    return parts[0], parts[1:]


def render_mobile_block(
    canvas: Canvas,
    raw: str,
    *,
    x: int,
    y: int,
    width: int,
    large_type: bool,
) -> int:
    kind, parts = block_parts(raw)
    title = parts[0] if parts else ""
    detail = parts[1] if len(parts) > 1 else ""
    body_size = 20 if large_type else 16
    if kind == "H":
        canvas.text_block((x, y), title, max_chars=14, size=26 if large_type else 22, bold=True)
        return 48 if large_type else 40
    if kind == "T":
        used = canvas.text_block(
            (x, y),
            title,
            max_chars=16 if large_type else 20,
            size=body_size,
            line_height=29 if large_type else 23,
            max_lines=3,
        )
        return used + 10
    if kind in {"C", "R"}:
        height = 84 if detail else 64
        canvas.rect((x, y, x + width, y + height), fill=PALETTE["surface"])
        canvas.text_block(
            (x + 14, y + 12), title, max_chars=17, size=body_size, bold=True, max_lines=1
        )
        if detail:
            canvas.text_block(
                (x + 14, y + 42),
                detail,
                max_chars=21,
                size=14 if not large_type else 17,
                fill=PALETTE["muted"],
                max_lines=2,
                line_height=21,
            )
        if kind == "R":
            canvas.circle(
                (x + width - 18, y + 20), 6, fill=PALETTE["dark"], outline=PALETTE["dark"]
            )
        return height + 12
    if kind == "F":
        canvas.text((x, y), title, size=14 if not large_type else 17, bold=True)
        canvas.rect((x, y + 24, x + width, y + 76), fill=PALETTE["surface"])
        canvas.text_block(
            (x + 12, y + 40),
            detail or "請輸入",
            max_chars=20,
            size=body_size,
            fill=PALETTE["muted"],
            max_lines=1,
        )
        return 90
    if kind in {"E", "N", "S"}:
        fill = "#E6E6E6" if kind != "E" else "#D8D8D8"
        canvas.rect((x, y, x + width, y + 68), fill=fill, outline=PALETTE["dark"], dash=kind == "N")
        label = {"E": "錯誤與下一步", "N": "設計註記", "S": "狀態"}[kind]
        canvas.text((x + 12, y + 10), label, size=12, fill=PALETTE["muted"], bold=True)
        canvas.text_block(
            (x + 12, y + 30), title, max_chars=22, size=15, max_lines=2, line_height=20
        )
        return 80
    if kind == "L":
        for offset, item_width in ((0, width), (48, int(width * 0.8))):
            canvas.rect(
                (x, y + offset, x + item_width, y + offset + 32),
                fill=PALETTE["soft"],
                outline=PALETTE["accent"],
            )
        canvas.text((x + 10, y + 8), title or "載入中…", size=13, fill=PALETTE["muted"])
        return 94
    if kind == "Q":
        size = min(128, width // 2)
        qx = x + (width - size) / 2
        canvas.rect((qx, y, qx + size, y + size), fill=PALETTE["surface"], outline=PALETTE["dark"])
        step = size / 6
        for row in range(6):
            for col in range(6):
                if (row * 3 + col * 5) % 4 in {0, 1}:
                    canvas.rect(
                        (
                            qx + col * step + 2,
                            y + row * step + 2,
                            qx + (col + 1) * step - 2,
                            y + (row + 1) * step - 2,
                        ),
                        fill=PALETTE["dark"],
                        outline=PALETTE["dark"],
                        radius=0,
                        width=1,
                    )
        canvas.text((x + width / 2, y + size + 9), title, size=14, anchor="ma")
        return size + 38
    if kind == "M":
        canvas.circle(
            (x + width / 2, y + 62), 52, fill=PALETTE["soft"], outline=PALETTE["dark"], width=4
        )
        canvas.line((x + width / 2, y + 36, x + width / 2, y + 70), fill=PALETTE["dark"], width=5)
        canvas.circle(
            (x + width / 2, y + 36), 11, fill=PALETTE["surface"], outline=PALETTE["dark"], width=3
        )
        canvas.text((x + width / 2, y + 122), title, size=15, bold=True, anchor="ma")
        return 150
    if kind in {"P", "D"}:
        height = 154
        canvas.rect(
            (x, y, x + width, y + height), fill=PALETTE["surface"], outline=PALETTE["dark"], width=3
        )
        canvas.text(
            (x + 14, y + 14), "系統權限對話框" if kind == "P" else "刪除確認", size=15, bold=True
        )
        canvas.text_block(
            (x + 14, y + 43), title, max_chars=20, size=15, max_lines=3, line_height=21
        )
        canvas.rect((x + 14, y + 111, x + width / 2 - 5, y + 142), fill=PALETTE["soft"])
        canvas.text((x + width / 4, y + 118), "稍後／取消", size=13, anchor="ma")
        canvas.rect(
            (x + width / 2 + 5, y + 111, x + width - 14, y + 142),
            fill=PALETTE["dark"],
            outline=PALETTE["dark"],
        )
        canvas.text((x + width * 0.75, y + 118), "允許／確認", size=13, fill="#FFFFFF", anchor="ma")
        return height + 12
    if kind == "B":
        canvas.rect((x, y, x + width, y + 48), fill=PALETTE["surface"], outline=PALETTE["dark"])
        canvas.text((x + width / 2, y + 14), title, size=16, bold=True, anchor="ma")
        return 60
    return 0


def render_mobile_wireframe(entry: dict[str, Any], svg_path: Path, png_path: Path) -> None:
    width = int(entry.get("width", 390))
    height = int(entry.get("height", 844))
    large_type = bool(entry.get("large_type"))
    canvas = Canvas(width, height)
    margin = 18 if width >= 390 else 14
    content_width = width - margin * 2

    canvas.rect(
        (0, 0, width, 25), fill=PALETTE["soft"], outline=PALETTE["accent"], radius=0, width=1
    )
    canvas.text((margin, 6), "安全區域", size=10, fill=PALETTE["muted"])
    canvas.text((width - margin, 6), "9:41", size=10, fill=PALETTE["muted"], anchor="ra")
    canvas.rect(
        (0, 25, width, 88), fill=PALETTE["surface"], outline=PALETTE["accent"], radius=0, width=1
    )
    canvas.text((margin, 40), entry["title"], size=20 if not large_type else 23, bold=True)
    canvas.text((margin, 68), entry["state"], size=12, fill=PALETTE["muted"])
    canvas.text((width - margin, 68), entry["role"], size=12, fill=PALETTE["muted"], anchor="ra")

    fixed_height = 96 if entry.get("primary") else 30
    scroll_bottom = height - fixed_height
    canvas.rect(
        (8, 96, width - 8, scroll_bottom - 8),
        fill=PALETTE["soft"],
        outline=PALETTE["line"],
        width=1,
        radius=6,
        dash=True,
    )
    canvas.text((margin, 100), "可捲動內容", size=10, fill=PALETTE["muted"])
    y = 122
    overflow = False
    for raw in entry.get("blocks", []):
        estimated = 90
        if y + estimated > scroll_bottom - 25:
            overflow = True
            break
        y += render_mobile_block(
            canvas,
            raw,
            x=margin,
            y=y,
            width=content_width,
            large_type=large_type,
        )
    if overflow:
        canvas.text(
            (width / 2, scroll_bottom - 27),
            "↓ 內容繼續，關鍵資訊不可截斷 ↓",
            size=12,
            fill=PALETTE["muted"],
            anchor="ma",
        )

    if entry.get("primary"):
        canvas.rect(
            (0, height - fixed_height, width, height),
            fill=PALETTE["surface"],
            outline=PALETTE["accent"],
            radius=0,
            width=1,
        )
        canvas.text(
            (margin, height - fixed_height + 6),
            "固定操作區／底部安全區域",
            size=10,
            fill=PALETTE["muted"],
        )
        canvas.rect(
            (margin, height - 66, width - margin, height - 18),
            fill=PALETTE["dark"],
            outline=PALETTE["dark"],
            radius=12,
        )
        canvas.text(
            (width / 2, height - 51),
            entry["primary"],
            size=17,
            fill="#FFFFFF",
            bold=True,
            anchor="ma",
        )
    else:
        canvas.text((margin, height - 19), "底部安全區域", size=10, fill=PALETTE["muted"])

    if entry.get("keyboard"):
        keyboard_top = height - 270
        canvas.rect(
            (0, keyboard_top, width, height),
            fill="#E0E0E0",
            outline=PALETTE["dark"],
            radius=0,
            dash=True,
        )
        canvas.text(
            (width / 2, keyboard_top + 20), "系統鍵盤可能覆蓋區", size=15, bold=True, anchor="ma"
        )
        for row in range(3):
            for col in range(8):
                key_width = (width - 34) / 8
                x1 = 12 + col * key_width
                y1 = keyboard_top + 52 + row * 47
                canvas.rect(
                    (x1, y1, x1 + key_width - 5, y1 + 34),
                    fill=PALETTE["surface"],
                    outline=PALETTE["line"],
                    radius=4,
                    width=1,
                )

    canvas.save(svg_path, png_path)


def render_admin_wireframe(entry: dict[str, Any], svg_path: Path, png_path: Path) -> None:
    width = int(entry.get("width", 1440))
    height = int(entry.get("height", 1024))
    canvas = Canvas(width, height)
    canvas.rect((0, 0, width, 86), fill=PALETTE["surface"], outline=PALETTE["dark"], radius=0)
    canvas.text((54, 25), "Kinsun 內部維運", size=26, bold=True)
    nav = ["總覽", "訊息流", "長輩", "系統"]
    for index, label in enumerate(nav):
        x = 460 + index * 150
        active = label in entry.get("active_nav", "")
        canvas.rect((x, 20, x + 126, 64), fill=PALETTE["dark"] if active else PALETTE["soft"])
        canvas.text(
            (x + 63, 34),
            label,
            size=16,
            fill="#FFFFFF" if active else PALETTE["ink"],
            bold=active,
            anchor="ma",
        )
    canvas.text((width - 54, 32), "X-Admin-Key", size=14, fill=PALETTE["muted"], anchor="ra")

    canvas.text((58, 120), entry["title"], size=30, bold=True)
    canvas.text(
        (58, 160), f"{entry['state']}｜1440 × 1024｜結構型線框", size=15, fill=PALETTE["muted"]
    )
    x = 58
    y = 205
    content_width = width - 116
    blocks = entry.get("blocks", [])
    columns = 3 if entry.get("template") in {"overview", "system"} else 2
    card_gap = 22
    card_width = (content_width - card_gap * (columns - 1)) / columns
    for index, raw in enumerate(blocks):
        kind, parts = block_parts(raw)
        title = parts[0] if parts else ""
        detail = parts[1] if len(parts) > 1 else ""
        col = index % columns
        row = index // columns
        card_x = x + col * (card_width + card_gap)
        card_y = y + row * 168
        if card_y + 145 > height - 40:
            break
        canvas.rect((card_x, card_y, card_x + card_width, card_y + 142), fill=PALETTE["surface"])
        label = {
            "E": "錯誤",
            "L": "載入",
            "F": "欄位",
            "C": "區塊",
            "R": "資料列",
            "T": "說明",
        }.get(kind, "區塊")
        canvas.text((card_x + 18, card_y + 14), label, size=12, fill=PALETTE["muted"], bold=True)
        canvas.text_block(
            (card_x + 18, card_y + 42),
            title,
            max_chars=22,
            size=19,
            bold=True,
            max_lines=2,
            line_height=27,
        )
        if detail:
            canvas.text_block(
                (card_x + 18, card_y + 96),
                detail,
                max_chars=31,
                size=14,
                fill=PALETTE["muted"],
                max_lines=2,
                line_height=20,
            )
    canvas.text(
        (width - 58, height - 30),
        "主要區域可捲動；鍵盤焦點依 DOM 順序移動。",
        size=14,
        fill=PALETTE["muted"],
        anchor="ra",
    )
    canvas.save(svg_path, png_path)


def render_wireframe(entry: dict[str, Any], svg_path: Path, png_path: Path) -> None:
    if entry.get("width", 390) >= 1000:
        render_admin_wireframe(entry, svg_path, png_path)
    else:
        render_mobile_wireframe(entry, svg_path, png_path)


def create_contact_sheet(
    contact: dict[str, Any],
    entries_by_id: dict[str, dict[str, Any]],
    manifest: list[dict[str, Any]],
) -> None:
    asset_ids = contact["asset_ids"]
    images: list[tuple[dict[str, Any], Image.Image]] = []
    is_admin = contact["id"] == "contact-admin"
    thumb_width = 650 if is_admin else 260
    columns = 2 if is_admin else 4
    label_height = 58
    thumb_height = 500
    cell_width = thumb_width + 36
    cell_height = thumb_height + label_height + 28
    for asset_id in asset_ids:
        entry = entries_by_id[asset_id]
        png_path = WIREFRAME_EXPORT / f"{asset_id}.png"
        with Image.open(png_path) as loaded:
            image = loaded.convert("RGB")
            image.thumbnail((thumb_width, thumb_height), Image.Resampling.LANCZOS)
            images.append((entry, image.copy()))

    rows = (len(images) + columns - 1) // columns
    sheet_width = 48 + columns * cell_width
    sheet_height = 120 + rows * cell_height + 36
    sheet = Image.new("RGB", (sheet_width, sheet_height), PALETTE["surface"])
    draw = ImageDraw.Draw(sheet)
    draw.text((34, 26), contact["title"], font=font(28, True), fill=PALETTE["ink"])
    draw.text(
        (34, 68),
        "灰階低保真｜縮圖供評審導覽，細節請開啟獨立 SVG",
        font=font(15),
        fill=PALETTE["muted"],
    )

    placements: list[tuple[dict[str, Any], Image.Image, int, int]] = []
    for index, (entry, image) in enumerate(images):
        col = index % columns
        row = index // columns
        cell_x = 34 + col * cell_width
        cell_y = 112 + row * cell_height
        image_x = cell_x + (thumb_width - image.width) // 2
        sheet.paste(image, (image_x, cell_y))
        draw.rectangle(
            (image_x, cell_y, image_x + image.width, cell_y + image.height),
            outline=PALETTE["line"],
            width=2,
        )
        draw.text(
            (cell_x, cell_y + thumb_height + 10),
            entry["title"],
            font=font(15, True),
            fill=PALETTE["ink"],
        )
        draw.text(
            (cell_x, cell_y + thumb_height + 34),
            entry["state"],
            font=font(13),
            fill=PALETTE["muted"],
        )
        placements.append((entry, image, image_x, cell_y))

    png_path = CONTACT_SHEETS / f"{contact['id']}.png"
    svg_path = CONTACT_SHEETS / f"{contact['id']}.svg"
    png_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(png_path, format="PNG", optimize=True)

    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{sheet_width}" height="{sheet_height}" '
        f'viewBox="0 0 {sheet_width} {sheet_height}" role="img">',
        f"<style>text{{font-family:{SVG_FONT_STACK};fill:{PALETTE['ink']};}}</style>",
        f'<rect width="{sheet_width}" height="{sheet_height}" fill="#FFFFFF"/>',
        (
            '<text x="34" y="52" font-size="28" font-weight="700">'
            f"{html.escape(contact['title'])}</text>"
        ),
        '<text x="34" y="86" font-size="15" fill="#5F6368">'
        "灰階低保真｜縮圖供評審導覽，細節請開啟獨立 SVG</text>",
    ]
    for entry, image, image_x, image_y in placements:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        svg_parts.append(
            f'<image x="{image_x}" y="{image_y}" width="{image.width}" height="{image.height}" '
            f'href="data:image/png;base64,{encoded}"/>'
        )
        svg_parts.append(
            f'<rect x="{image_x}" y="{image_y}" width="{image.width}" height="{image.height}" '
            'fill="none" stroke="#9AA0A6" stroke-width="2"/>'
        )
        cell_x = image_x - max(0, (thumb_width - image.width) // 2)
        svg_parts.append(
            f'<text x="{cell_x}" y="{image_y + thumb_height + 27}" font-size="15" '
            f'font-weight="700">{html.escape(entry["title"])}</text>'
        )
        svg_parts.append(
            f'<text x="{cell_x}" y="{image_y + thumb_height + 50}" font-size="13" '
            f'fill="#5F6368">{html.escape(entry["state"])}</text>'
        )
    svg_parts.append("</svg>")
    save_text(svg_path, "\n".join(svg_parts))

    manifest.append(
        {
            "id": contact["id"],
            "title": contact["title"],
            "type": "contact-sheet",
            "role": contact["role"],
            "screen": "多畫面評審索引",
            "state": "彙整",
            "source_path": repo_relative(WIREFRAME_SOURCE / "wireframe-spec.json"),
            "svg_path": repo_relative(svg_path),
            "png_path": repo_relative(png_path),
            "related_document": "docs/uiux/07-wireframe-specification.md",
            "status": "第二階段評審稿",
        }
    )


def check_markdown_images() -> list[str]:
    problems: list[str] = []
    image_pattern = re.compile(r"!\[[^\]]*]\(([^)]+)\)")
    for markdown_path in UIUX_ROOT.glob("*.md"):
        content = markdown_path.read_text(encoding="utf-8")
        for raw_path in image_pattern.findall(content):
            target = raw_path.split("#", 1)[0]
            if target.startswith(("http://", "https://")):
                continue
            resolved = (markdown_path.parent / target).resolve()
            if not resolved.is_file():
                problems.append(f"{repo_relative(markdown_path)} -> {target}")
    return problems


def validate_assets(manifest: list[dict[str, Any]]) -> None:
    required = {
        "id",
        "title",
        "type",
        "role",
        "screen",
        "state",
        "source_path",
        "svg_path",
        "png_path",
        "related_document",
        "status",
    }
    errors: list[str] = []
    seen: set[str] = set()
    for asset in manifest:
        missing = required - asset.keys()
        if missing:
            errors.append(f"{asset.get('id', '?')} manifest 缺欄位：{sorted(missing)}")
        if asset["id"] in seen:
            errors.append(f"重複 id：{asset['id']}")
        seen.add(asset["id"])
        for key in ("source_path", "svg_path", "png_path", "related_document"):
            path = REPO_ROOT / asset[key]
            if not path.is_file():
                errors.append(f"{asset['id']} 缺少 {key}：{asset[key]}")
        svg_path = REPO_ROOT / asset["svg_path"]
        if svg_path.is_file():
            source = svg_path.read_text(encoding="utf-8")
            try:
                root = ET.fromstring(source)
                if not root.attrib.get("viewBox"):
                    errors.append(f"{asset['id']} SVG 缺 viewBox")
            except ET.ParseError as exc:
                errors.append(f"{asset['id']} SVG 解析失敗：{exc}")
            if re.search(r"(?:href|xlink:href|src)=[\"']https?://", source):
                errors.append(f"{asset['id']} SVG 含外部 URL")
            if "Lorem" in source or "lorem" in source:
                errors.append(f"{asset['id']} SVG 含 Lorem")
        png_path = REPO_ROOT / asset["png_path"]
        if png_path.is_file():
            with Image.open(png_path) as image:
                rgb = image.convert("RGB")
                extrema = rgb.getextrema()
                if all(channel == (255, 255) for channel in extrema):
                    errors.append(f"{asset['id']} PNG 為空白")

    errors.extend(f"Markdown 圖片路徑失效：{item}" for item in check_markdown_images())
    if errors:
        raise RuntimeError("資產驗證失敗：\n- " + "\n- ".join(errors))


def main() -> None:
    for directory in (
        DIAGRAM_SOURCE,
        DIAGRAM_EXPORT,
        WIREFRAME_SOURCE,
        WIREFRAME_EXPORT,
        CONTACT_SHEETS,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    diagram_spec = load_json(DIAGRAM_SOURCE / "diagram-spec.json")
    wireframe_spec = load_json(WIREFRAME_SOURCE / "wireframe-spec.json")
    manifest: list[dict[str, Any]] = []

    for entry in diagram_spec["assets"]:
        source_svg = DIAGRAM_SOURCE / f"{entry['id']}.svg"
        source_mmd = DIAGRAM_SOURCE / f"{entry['id']}.mmd"
        export_svg = DIAGRAM_EXPORT / f"{entry['id']}.svg"
        export_png = DIAGRAM_EXPORT / f"{entry['id']}.png"
        render_diagram(entry, source_svg, export_png)
        shutil.copyfile(source_svg, export_svg)
        save_text(source_mmd, mermaid_source(entry))
        manifest.append(
            {
                "id": entry["id"],
                "title": entry["title"],
                "type": entry["type"],
                "role": entry["role"],
                "screen": entry["screen"],
                "state": entry.get("state", "架構"),
                "source_path": repo_relative(source_mmd),
                "svg_path": repo_relative(export_svg),
                "png_path": repo_relative(export_png),
                "related_document": entry["related_document"],
                "status": entry.get("status", "第一階段評審稿"),
            }
        )

    entries_by_id: dict[str, dict[str, Any]] = {}
    for entry in wireframe_spec["assets"]:
        entries_by_id[entry["id"]] = entry
        source_svg = WIREFRAME_SOURCE / f"{entry['id']}.svg"
        export_svg = WIREFRAME_EXPORT / f"{entry['id']}.svg"
        export_png = WIREFRAME_EXPORT / f"{entry['id']}.png"
        render_wireframe(entry, source_svg, export_png)
        shutil.copyfile(source_svg, export_svg)
        manifest.append(
            {
                "id": entry["id"],
                "title": entry["title"],
                "type": "wireframe",
                "role": entry["role"],
                "screen": entry["screen"],
                "state": entry["state"],
                "source_path": repo_relative(source_svg),
                "svg_path": repo_relative(export_svg),
                "png_path": repo_relative(export_png),
                "related_document": "docs/uiux/07-wireframe-specification.md",
                "status": entry.get("status", "第二階段評審稿"),
            }
        )

    for contact in wireframe_spec["contact_sheets"]:
        create_contact_sheet(contact, entries_by_id, manifest)

    save_text(
        MANIFEST_PATH,
        json.dumps(
            {
                "schema_version": "1.0",
                "generated_at": "2026-07-27",
                "generator": "docs/uiux/tools/generate_assets.py",
                "asset_count": len(manifest),
                "assets": manifest,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    validate_assets(manifest)
    diagram_count = len(diagram_spec["assets"])
    wireframe_count = len(wireframe_spec["assets"])
    contact_count = len(wireframe_spec["contact_sheets"])
    print(
        f"完成：{diagram_count} 張圖表、{wireframe_count} 張線框、"
        f"{contact_count} 張 Contact Sheet；manifest 共 {len(manifest)} 筆。"
    )
    print(f"PNG 字型：{FONT_PATH or 'Pillow 預設字型（未找到 CJK 系統字型）'}")
    print("驗證：SVG/XML、viewBox、外部 URL、Lorem、PNG 非空白、manifest 路徑皆通過。")


if __name__ == "__main__":
    main()
