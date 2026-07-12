"""密碼雜湊：標準庫 scrypt，零新依賴。

儲存格式 ``scrypt$<n>$<r>$<p>$<salt_hex>$<hash_hex>``——參數隨值保存，
日後調參只影響新密碼，舊值仍可驗證。
"""

from __future__ import annotations

import hashlib
import hmac
import os

# 生產成本參數（✅ 庚-20／A-50）：N=2**17 為 OWASP 2024 建議下限。
# 測試環境由 tests/conftest.py 降為 2**14 加速；參數隨值存，互不影響驗證。
PROD_SCRYPT_N = 131072  # 2**17
_N = PROD_SCRYPT_N
_R = 8
_P = 1
_DKLEN = 32
_SALT_BYTES = 16


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    # scrypt 記憶體需求 ≈ 128×r×N bytes（N=2**17、r=8 → ~134MB），
    # OpenSSL 預設 maxmem 32MB 不夠——按參數動態給足並留餘裕。
    maxmem = 128 * r * n + 32 * 1024 * 1024
    return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=_DKLEN, maxmem=maxmem)


def hash_password(password: str) -> str:
    salt = os.urandom(_SALT_BYTES)
    digest = _derive(password, salt, _N, _R, _P)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    parts = stored.split("$")
    if len(parts) != 6 or parts[0] != "scrypt":
        return False
    try:
        n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
        salt, expected = bytes.fromhex(parts[4]), bytes.fromhex(parts[5])
        digest = _derive(password, salt, n, r, p)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, expected)
