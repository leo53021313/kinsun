"""MedicationStore 合約：Fake 與 Pg 兩個 adapter 必須對同一情境給出相同結果。

Fake 每次都跑；Pg 需 `KINSUN_IT=1`（連真庫）。斷言一律以 `ns` 前綴 scope 到
本測試自己的資料，才能在共用真庫上以「成員／排除」關係斷言而互不干擾。
"""

from __future__ import annotations

import pytest

from kinsun.medications.models import Medication, MedicationSlot
from kinsun.medications.store import FakeMedicationStore, PgMedicationStore

M = MedicationSlot


def _med(medication_id: str, elder_id: str, name: str, slots: tuple[MedicationSlot, ...]):
    return Medication(medication_id, elder_id, name, slots)


@pytest.fixture(params=["fake", "pg"])
def store(request):
    if request.param == "pg":
        return PgMedicationStore(request.getfixturevalue("pg_database"))
    return FakeMedicationStore()


def test_list_for_elder_sorted_by_name(store, ns):
    # 存入順序刻意與排序相反，證明回傳是「依 name 排序」而非「依存入順序」。
    store.save(_med(f"{ns}m1", f"{ns}e1", "2號藥", (M.MORNING,)))
    store.save(_med(f"{ns}m2", f"{ns}e1", "1號藥", (M.BEDTIME,)))
    assert [m.name for m in store.list_for_elder(f"{ns}e1")] == ["1號藥", "2號藥"]


def test_list_for_slot_is_set_membership(store, ns):
    store.save(_med(f"{ns}m1", f"{ns}e1", "早藥", (M.MORNING,)))
    store.save(_med(f"{ns}m2", f"{ns}e1", "午藥", (M.NOON,)))
    morning = {m.medication_id for m in store.list_for_slot(M.MORNING)}
    assert f"{ns}m1" in morning
    assert f"{ns}m2" not in morning


def test_multi_slot_med_matches_each_of_its_slots(store, ns):
    store.save(_med(f"{ns}m1", f"{ns}e1", "早晚藥", (M.MORNING, M.EVENING)))
    assert f"{ns}m1" in {m.medication_id for m in store.list_for_slot(M.MORNING)}
    assert f"{ns}m1" in {m.medication_id for m in store.list_for_slot(M.EVENING)}
    assert f"{ns}m1" not in {m.medication_id for m in store.list_for_slot(M.NOON)}


def test_save_upserts_on_conflict(store, ns):
    store.save(_med(f"{ns}m1", f"{ns}e1", "原名", (M.MORNING,)))
    store.save(_med(f"{ns}m1", f"{ns}e1", "改名", (M.NOON,)))
    got = [m for m in store.list_for_elder(f"{ns}e1") if m.medication_id == f"{ns}m1"]
    assert len(got) == 1
    assert got[0].name == "改名"
    assert got[0].slots == (M.NOON,)


def test_remove_deletes(store, ns):
    store.save(_med(f"{ns}m1", f"{ns}e1", "藥", (M.MORNING,)))
    store.remove(f"{ns}m1")
    assert all(m.medication_id != f"{ns}m1" for m in store.list_for_elder(f"{ns}e1"))
