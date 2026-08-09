import pytest

from kinsun.rag.ingest import ResetGuardError, ensure_reset_is_safe


def test_reset_is_allowed_when_nothing_is_serving():
    """沒有正在服務的版本時，--reset 不需要任何額外確認。"""
    ensure_reset_is_safe(None, force_reset=False)


def test_reset_is_blocked_while_a_release_is_serving():
    """有 active release 時擋下 --reset。

    2026-08-07 實錄：換衛福部來源設定時沿用了上一輪的 `--reset`，把已經上線的
    `rag-20260805T115255Z`（3,651 篇）連同全部 chunk 直接刪掉，衛教問答空窗四
    小時。清空並非換版的必要步驟——不加 `--reset` 時舊版會繼續服務，直到新版
    通過品質閘門才接手，這正是 release 機制存在的理由。
    """
    with pytest.raises(ResetGuardError) as error:
        ensure_reset_is_safe("rag-20260805T115255Z", force_reset=False)

    message = str(error.value)
    assert "rag-20260805T115255Z" in message, "要指名會被刪掉的是哪一版"
    assert "--force-reset" in message, "要告訴操作者怎麼在確定要刪時繼續"


def test_reset_proceeds_when_the_operator_says_so():
    """明確加了 --force-reset 就照做——護欄擋的是手滑，不是擋人。"""
    ensure_reset_is_safe("rag-20260805T115255Z", force_reset=True)


def test_reset_is_blocked_while_a_build_is_in_flight():
    """建置中的版本同樣要擋——它代表數小時的抓取成果。

    `get_active()` 只認 `active`，建置中的是 `building`；不一起擋的話，重建跑到
    一半時另一個人下 `--reset`，四小時的抓取會無聲消失。既有的
    `uq_rag_release_building` 唯一約束擋不住這條路：`--reset` 是先刪再建，
    刪完約束就不成立了。
    """
    with pytest.raises(ResetGuardError) as error:
        ensure_reset_is_safe(None, building="rag-20260807T054725Z", force_reset=False)

    assert "rag-20260807T054725Z" in str(error.value)


def test_stale_build_can_still_be_cleared_with_the_explicit_flag():
    """建置中途掛掉會留下 building 列，--force-reset 是它的逃生口。"""
    ensure_reset_is_safe(None, building="rag-20260807T054725Z", force_reset=True)
