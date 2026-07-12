"""密碼雜湊模組測試：scrypt 往返、鹽隨機性、壞輸入防禦。"""

from kinsun.accounts.passwords import hash_password, verify_password


def test_hash_and_verify_roundtrip():
    stored = hash_password("correct-horse-battery")
    assert stored.startswith("scrypt$16384$8$1$")
    assert verify_password("correct-horse-battery", stored) is True


def test_wrong_password_rejected():
    stored = hash_password("正確密碼123")
    assert verify_password("錯誤密碼123", stored) is False
    assert verify_password("", stored) is False


def test_salt_is_random_per_hash():
    a = hash_password("同一組密碼")
    b = hash_password("同一組密碼")
    assert a != b
    assert verify_password("同一組密碼", a) and verify_password("同一組密碼", b)


def test_malformed_stored_value_rejected():
    assert verify_password("x", "") is False
    assert verify_password("x", "plaintext") is False
    assert verify_password("x", "scrypt$16384$8$1$deadbeef") is False  # 缺 hash 段
    assert verify_password("x", "scrypt$abc$8$1$00$00") is False  # 參數非數字


def test_production_cost_meets_owasp_2024(monkeypatch):
    """✅ 庚-20（A-50）：生產 scrypt N＝2**17（OWASP 2024 建議）。

    conftest 為測試速度把 _N 降為 2**14，此處還原生產值實跑一次
    （~200ms）確認可雜湊、可驗證、maxmem 足夠。
    """
    from kinsun.accounts import passwords

    assert passwords.PROD_SCRYPT_N == 2**17
    monkeypatch.setattr(passwords, "_N", passwords.PROD_SCRYPT_N)
    stored = hash_password("sunsun-8888")
    assert stored.startswith("scrypt$131072$8$1$")
    assert verify_password("sunsun-8888", stored) is True
