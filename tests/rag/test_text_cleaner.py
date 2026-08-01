"""衛教文字清理：全形空白、連續空白、多重空行、首尾修剪。"""

from __future__ import annotations

from kinsun.rag.text_cleaner import clean_text


def test_fullwidth_space_becomes_halfwidth():
    assert clean_text("量　血壓") == "量 血壓"


def test_collapses_runs_of_spaces_and_tabs():
    assert clean_text("規律  量\t\t血壓") == "規律 量 血壓"


def test_strips_each_line_and_collapses_blank_lines():
    text = "第一段  \n\n\n\n第二段"
    assert clean_text(text) == "第一段\n\n第二段"


def test_strips_leading_and_trailing_whitespace():
    assert clean_text("\n  高血壓衛教  \n") == "高血壓衛教"


def test_empty_input_stays_empty():
    assert clean_text("") == ""


def test_strips_nul_bytes():
    """Postgres text 欄位不接受 NUL（0x00），清理時一併移除。"""
    assert clean_text("高血壓\x00衛教") == "高血壓衛教"


def test_strips_view_counter_lines():
    """點閱計數行每次請求都在變，會讓同一頁的內容雜湊永遠不同、每輪重嵌
    （2026-07-27 實測 hpa Detail 頁兩次抓取唯一差異＝點閱次數 +1）；對檢索也毫無價值。"""
    text = "高血壓衛教重點\n點閱次數：166556\n規律量血壓"
    assert clean_text(text) == "高血壓衛教重點\n規律量血壓"
    assert clean_text("瀏覽人次: 1,234") == ""
    assert clean_text("觀看次數：42") == ""
    # 內文提及次數的完整句子不可誤殺
    assert (
        clean_text("這支影片的點閱次數：破百萬，很受長輩歡迎")
        == "這支影片的點閱次數：破百萬，很受長輩歡迎"
    )


_DEBUNK_PAGE = """衛生福利部國民健康署 - 不運動就瘦不下來嗎？
跳到主要內容區塊
:::
真相與闢謠
保健闢謠
定位點
:::
首頁
>
服務園地
>
保健闢謠
不運動就瘦不下來嗎？
facebook
列印
發布單位：社區健康組
發布日期：2019/12/03
事實上相較於運動，飲食控制對減重的效果更明顯，但合併運動有更多健康益處。
【可以這樣做】
減重時，除了飲食控制之外也應合併運動。
資料來源：台灣肥胖醫學會
上一則
您可能會喜歡
老人家血壓太高沒關係？
菠菜與豆腐一起吃，真的會導致結石嗎？
看完本篇主題後，您的感覺如何？
回上頁
回首頁"""


def test_strip_page_furniture_removes_navigation_meta_and_related_articles():
    from kinsun.rag.text_cleaner import strip_page_furniture

    body = strip_page_furniture(_DEBUNK_PAGE, title="不運動就瘦不下來嗎？")

    assert "事實上相較於運動，飲食控制對減重的效果更明顯" in body
    assert "【可以這樣做】" in body
    assert "資料來源：台灣肥胖醫學會" in body
    for furniture in (
        "跳到主要內容區塊",
        ":::",
        "定位點",
        "facebook",
        "發布單位",
        "發布日期",
        "回上頁",
        "回首頁",
    ):
        assert furniture not in body, furniture
    # 文末「您可能會喜歡」會夾帶其他文章標題，留著等於把 A 的向量污染成 B
    assert "老人家血壓太高沒關係？" not in body
    assert "菠菜與豆腐一起吃" not in body


def test_strip_page_furniture_keeps_short_debunk_articles():
    """短不等於空。

    「保健闢謠」整篇常常只有 100 字上下就把事情講完，那是全庫最貼近長輩提問的
    內容。2026-08-01 我一度用「內文少於 150 字就排除」，會一口氣砍掉 557 篇這種
    文章——這個測試就是為了讓那個錯誤再也不會悄悄發生。
    """
    from kinsun.rag.text_cleaner import strip_page_furniture

    page = """衛生福利部國民健康署 - 連喝水也會胖
跳到主要內容區塊
:::
保健闢謠
定位點
:::
首頁
>
服務園地
>
保健闢謠
連喝水也會胖
facebook
列印
發布日期：2019/12/03
身體熱量的來源主要來自食物中的醣類、脂肪和蛋白質。維生素、礦物質和水分不會產生熱量，所以正常喝水並不會增加體重。
上一則
回首頁"""

    body = strip_page_furniture(page, title="連喝水也會胖")

    assert body.startswith("身體熱量的來源")
    assert "正常喝水並不會增加體重" in body
    # 整篇只有 50 幾字，仍必須完整留下——長度不是判斷有沒有內容的依據
    assert len(body) >= 50


def test_strip_page_furniture_keeps_body_when_dates_appear_after_it():
    """另一種版型：發布日期排在正文之後，不可因此把正文一起截掉。"""
    from kinsun.rag.text_cleaner import strip_page_furniture

    page = """衛生福利部國民健康署 - 本署召開國民營養促進法草案座談會
跳到主要內容區塊
:::
大事紀要
115年
103年
定位點
:::
首頁
>
關於本署
>
大事紀要
>
103年
本署召開國民營養促進法草案座談會
本署於12月26日辦理103年社區健康營造成果發表會，表揚推動健康促進之績優單位。
發布日期：2014-12-25
更新日期：2020-03-20
看完本篇主題後，您的感覺如何？
回上頁
回首頁"""

    body = strip_page_furniture(page, title="本署召開國民營養促進法草案座談會")

    assert "12月26日辦理103年社區健康營造成果發表會" in body
    assert "看完本篇主題後" not in body
    assert "發布日期" not in body


def test_strip_page_furniture_leaves_plain_text_untouched():
    """沒有樣板的純文字（例如 PDF 抽出的內容）不該被動到。"""
    from kinsun.rag.text_cleaner import strip_page_furniture

    plain = "高血壓的長者應規律量血壓。\n飲食以少油少鹽為原則。\n每週至少運動一百五十分鐘。"

    assert strip_page_furniture(plain, title="高血壓照護") == plain


def test_strip_page_furniture_does_not_cut_on_arrow_inside_body():
    """正文裡出現「>」不該被誤判成麵包屑而截掉前文。"""
    from kinsun.rag.text_cleaner import strip_page_furniture

    page = """血壓分級說明
收縮壓 140 mmHg 以上為高血壓。
>
以上分級依國民健康署建議。"""

    body = strip_page_furniture(page, title="血壓分級說明")

    assert "收縮壓 140 mmHg 以上為高血壓。" in body
