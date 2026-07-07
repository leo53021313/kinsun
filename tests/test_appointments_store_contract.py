"""AppointmentStore 合約：Fake 與 Pg 兩個 adapter 必須對同一情境給出相同結果。

Fake 每次都跑；Pg 需 `KINSUN_IT=1`（連真庫）。斷言一律以 `ns` 前綴 scope 到
本測試自己的資料，才能在共用真庫上以「成員／排除」關係斷言而互不干擾。

注意：`list_for_date` 未以 elder_id scope，跨測試會撞同一天資料，故只驗成員／
排除、不做整份清單相等；`list_for_elder` 以獨一無二的 ns elder_id scope，可整份相等。
"""

from __future__ import annotations

import pytest

from kinsun.appointments.models import Appointment
from kinsun.appointments.store import FakeAppointmentStore, PgAppointmentStore


def _appt(appointment_id: str, elder_id: str, date: str, label: str) -> Appointment:
    return Appointment(appointment_id, elder_id, date, label)


@pytest.fixture(params=["fake", "pg"])
def store(request):
    if request.param == "pg":
        return PgAppointmentStore(request.getfixturevalue("pg_database"))
    return FakeAppointmentStore()


def test_list_for_elder_sorted_by_date(store, ns):
    # 存入順序刻意與排序相反，證明回傳是「依 date 排序」而非「依存入順序」。
    store.save(_appt(f"{ns}a1", f"{ns}e1", "2026-07-15", "心臟科回診"))
    store.save(_appt(f"{ns}a2", f"{ns}e1", "2026-07-01", "眼科回診"))
    assert [a.date for a in store.list_for_elder(f"{ns}e1")] == ["2026-07-01", "2026-07-15"]


def test_list_for_date_is_set_membership(store, ns):
    store.save(_appt(f"{ns}a1", f"{ns}e1", "2026-07-15", "當天回診"))
    store.save(_appt(f"{ns}a2", f"{ns}e1", "2026-07-16", "隔天回診"))
    on_15th = {a.appointment_id for a in store.list_for_date("2026-07-15")}
    assert f"{ns}a1" in on_15th
    assert f"{ns}a2" not in on_15th


def test_save_upserts_on_conflict(store, ns):
    store.save(_appt(f"{ns}a1", f"{ns}e1", "2026-07-15", "原名"))
    store.save(_appt(f"{ns}a1", f"{ns}e1", "2026-07-20", "改名"))
    got = [a for a in store.list_for_elder(f"{ns}e1") if a.appointment_id == f"{ns}a1"]
    assert len(got) == 1
    assert got[0].label == "改名"
    assert got[0].date == "2026-07-20"


def test_remove_deletes(store, ns):
    store.save(_appt(f"{ns}a1", f"{ns}e1", "2026-07-15", "回診"))
    store.remove(f"{ns}a1")
    assert all(a.appointment_id != f"{ns}a1" for a in store.list_for_elder(f"{ns}e1"))
    assert f"{ns}a1" not in {a.appointment_id for a in store.list_for_date("2026-07-15")}
