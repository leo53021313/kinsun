from kinsun.channels.line.richmenu import build_rich_menu_request


def test_build_rich_menu_request_opens_liff():
    req = build_rich_menu_request("1234-ab")
    assert req.size.width == 2500
    assert req.size.height == 843
    assert req.chat_bar_text == "家屬選單"
    assert len(req.areas) == 1
    assert req.areas[0].action.uri == "https://liff.line.me/1234-ab"
