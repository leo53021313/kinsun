"""合約測試共用夾具。

- `ns`：每個測試獨立的識別字前綴，讓合約能在「共用真庫」上以成員關係斷言、互不干擾。
- `pg_database`：連上真庫（已建表）；未設 `KINSUN_IT=1` 時整批 skip，session 內只開一次。
"""

from __future__ import annotations

import os
import uuid

import pytest


@pytest.fixture
def ns() -> str:
    return f"ct-{uuid.uuid4().hex[:8]}-"


@pytest.fixture(scope="session")
def pg_database():
    if os.environ.get("KINSUN_IT") != "1":
        pytest.skip("需 KINSUN_IT=1 與 DATABASE_URL（連真庫）")
    from kinsun.db import Database, ensure_schema

    url = os.environ["DATABASE_URL"]
    ensure_schema(url)
    db = Database.open(url)
    yield db
    db.close()
