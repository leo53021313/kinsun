"""家屬圖文選單佈建：建立開啟 LIFF 的 Rich Menu（一次性，對真 LINE 執行）。

CLI：
  LINE_CHANNEL_ACCESS_TOKEN=... LIFF_ID=... \
  PYTHONPATH=src uv run python -m kinsun.channels.line.richmenu <image_path>
印出 rich_menu_id；設為環境變數 RICH_MENU_ID，家屬綁定時會 link 給該使用者。
圖片規格：2500x843、<=1MB、png/jpeg（png 上傳 content-type image/png）。
"""

from __future__ import annotations

import os
import sys

from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    MessagingApiBlob,
    RichMenuArea,
    RichMenuBounds,
    RichMenuRequest,
    RichMenuSize,
    URIAction,
)

_WIDTH = 2500
_HEIGHT = 843


def build_rich_menu_request(liff_id: str) -> RichMenuRequest:
    return RichMenuRequest(
        size=RichMenuSize(width=_WIDTH, height=_HEIGHT),
        selected=True,
        name="家屬選單",
        chat_bar_text="家屬選單",
        areas=[
            RichMenuArea(
                bounds=RichMenuBounds(x=0, y=0, width=_WIDTH, height=_HEIGHT),
                action=URIAction(uri=f"https://liff.line.me/{liff_id}", label="開啟家屬儀表板"),
            )
        ],
    )


def setup_rich_menu(access_token: str, liff_id: str, image_path: str) -> str:
    config = Configuration(access_token=access_token)
    with ApiClient(config) as client:
        rich_menu_id = (
            MessagingApi(client).create_rich_menu(build_rich_menu_request(liff_id)).rich_menu_id
        )
        with open(image_path, "rb") as image:
            MessagingApiBlob(client).set_rich_menu_image(rich_menu_id, body=image.read())
    return rich_menu_id


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print("用法：python -m kinsun.channels.line.richmenu <image_path>")
        return 1
    token = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
    liff_id = os.environ["LIFF_ID"]
    rich_menu_id = setup_rich_menu(token, liff_id, args[0])
    print(f"rich_menu_id={rich_menu_id}")
    print("請把它設為環境變數 RICH_MENU_ID，家屬綁定時會自動 link。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
