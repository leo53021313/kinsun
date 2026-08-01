"""收錄判定：把「行政文書」與「沒有實質內容的空殼」擋在 RAG 之外。"""

from kinsun.rag.content_filter import judge_admission


def test_health_education_article_is_admitted():
    verdict = judge_admission(
        title="不運動就瘦不下來嗎？",
        content="事實上相較於運動，飲食控制對減重的效果更明顯。運動可以有效降低體脂肪及內臟脂肪。",
    )

    assert verdict.is_admitted
    assert verdict.reason == ""


def test_short_debunk_article_is_admitted():
    """短不等於空——「保健闢謠」常常 100 字內就把事情講完。

    2026-08-01 我一度以「內文少於 150 字」為門檻，會砍掉 557 篇這種文章；
    它們正是最貼近長輩提問的內容。這個測試守住那條界線。
    """
    verdict = judge_admission(
        title="連喝水也會胖",
        content="維生素、礦物質和水分不會產生熱量，但水分本是人體所需。所以正常喝水並不會增加體重。",
    )

    assert verdict.is_admitted


def test_attachment_only_page_is_rejected_as_shell():
    """網頁本身沒有內容，東西全在 PDF 附件裡。"""
    verdict = judge_admission(
        title="國民健康署114年菸害防制計畫評核結果",
        content="附件\n2026-01-29\n45KB\n衛生福利部國民健康署114年度計畫評核結果.pdf",
    )

    assert not verdict.is_admitted
    assert verdict.reason == "空殼"


def test_title_echo_page_is_rejected_as_shell():
    """內文只是把標題再讀一次，沒有新資訊。

    內文刻意寫得比長度門檻長，確保測到的是「標題複讀」這條規則本身，
    而不是被長度不足先攔下來。
    """
    title = "公告修正「衛生福利部國民健康署醫事機構戒菸服務違規處置審議會設置要點」第三點及第五點"
    verdict = judge_admission(title=title, content=f"{title}，並自公告日起生效。")

    assert not verdict.is_admitted
    assert verdict.reason == "空殼"


def test_administrative_documents_are_rejected():
    for title in (
        "107年國民健康署法定預算",
        "公開委託辦理「網路調查入口平台建置」",
        "108年度菸害防制及保健基金-出國計畫執行情形",
        "112年5月份基金會計月報",
        "國家廉政建設行動方案",
        "發布修正「戒菸教育實施辦法」",
    ):
        verdict = judge_admission(
            title=title,
            content=(
                "本案依相關規定辦理，詳如附件所載之內容與作業程序說明，並自公告日起生效施行，"
                "請各相關單位配合辦理；如對本案內容有疑義，請逕洽本署承辦人員查詢。"
            ),
        )
        assert not verdict.is_admitted, title
        assert verdict.reason == "行政文書", title


def test_trail_guide_is_rejected():
    """健走步道／景點導覽：跟健康促進有關，但回答不了健康問題。"""
    verdict = judge_admission(
        title="八卦山健康步道",
        content=(
            "健走範圍：八卦山大佛風景區\n健走公里數：2.5 公里\n"
            "環境特色：林蔭步道，沿途設有休憩座椅。\n交通方式：\n自行開車：國道一號彰化交流道下。"
        ),
    )

    assert not verdict.is_admitted
    assert verdict.reason == "步道導覽"


def test_article_mentioning_a_park_is_still_admitted():
    """只是提到公園的衛教文，不可被誤判成步道導覽。

    2026-08-01 我第一版用關鍵字比對，把〈做身體活動好像很花錢〉這類文章也算進
    步道，數量從 150 灌水到 482；步道頁真正的特徵是那組固定欄位，不是關鍵字。
    """
    verdict = judge_admission(
        title="做身體活動好像很花錢，是不是需要專業的設備跟服裝呢?",
        content=(
            "其實不需要。走路、爬樓梯、做家事都算身體活動，到住家附近的公園快走就有效果，"
            "穿著舒適合腳的鞋子即可，不必添購專業裝備。"
        ),
    )

    assert verdict.is_admitted


def test_english_only_article_is_rejected():
    verdict = judge_admission(
        title="E-cigarettes pose threat to teen health: HPA",
        content="The Health Promotion Administration today warned that e-cigarette use has risen.",
    )

    assert not verdict.is_admitted
    assert verdict.reason == "英文稿"


def test_redirect_only_faq_is_rejected():
    """只叫人去別處看的問答沒有回答價值，當作空殼擋掉。

    2026-08-01 用真實語料校準長度門檻：30～39 字那一帶共 18 篇，沒有一篇是真衛教，
    全是公告、表單指引與這種空轉問答。40 字這個門檻是這樣定出來的，不是拍腦袋。
    """
    verdict = judge_admission(
        title="哪裡可以查詢到乳癌相關資訊？",
        content="「乳癌」相關資訊請參考本網站乳癌防治問答集。",
    )

    assert not verdict.is_admitted
    assert verdict.reason == "空殼"


def test_institution_facing_procedure_documents_are_still_admitted():
    """「作業說明」類刻意保留——民眾申辦補助時會問，不算完全無關。

    Leo 核定的收錄原則是「文章越多越好，只擋完全無關的」，
    這條測試把那個取捨釘住，避免之後有人順手把它們一起濾掉。
    """
    verdict = judge_admission(
        title="體外受精(俗稱試管嬰兒)人工生殖技術補助方案民眾申辦作業說明",
        content=(
            "符合資格的不孕夫妻可向本署特約人工生殖機構提出申請，"
            "檢附診斷證明與相關文件，每次療程最高補助新臺幣十萬元，補助次數依年齡分級。"
        ),
    )

    assert verdict.is_admitted


def test_link_only_page_is_rejected_as_shell():
    """整頁只有一個外部連結，沒有可回答的內容。

    2026-08-01 對真實網站煙霧測試時抓到的：〈秋行軍蟲通報管道 0800-039-131〉
    內文只有一個 facebook 網址，卻因為網址夠長而通過長度門檻。
    """
    verdict = judge_admission(
        title="秋行軍蟲通報管道 0800-039-131",
        content="https://www.facebook.com/coataiwan/photos/a.1661824860809011/2322819928042831/?type=3",
    )

    assert not verdict.is_admitted
    assert verdict.reason == "空殼"


def test_attachment_index_page_is_rejected_even_with_repeated_title():
    """附件索引頁：內文只有標題重複與附件清單。"""
    verdict = judge_admission(
        title="臺灣健康不平等報告-全文電子檔",
        content=(
            "臺灣健康不平等報告-全文電子檔\n附件\n2017-03-28\n8MB\n"
            "臺灣健康不平等報告-全文電子檔.pdf\n2017-10-13\n14MB\n臺灣健康不平等報告中譯本.pdf"
        ),
    )

    assert not verdict.is_admitted
    assert verdict.reason == "空殼"
