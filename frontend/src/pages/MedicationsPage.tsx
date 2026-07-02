import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  type Medication,
  addMedication,
  deleteMedication,
  listMedications,
  updateMedication,
} from "../api";
import { SLOTS, slotLabel } from "../medicationSlots";

export function MedicationsPage() {
  const { elderId = "" } = useParams();
  const [meds, setMeds] = useState<Medication[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [slots, setSlots] = useState<string[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);

  const reload = useCallback(() => {
    listMedications(elderId)
      .then(setMeds)
      .catch(() => setError("載入失敗，請稍後再試"));
  }, [elderId]);

  useEffect(reload, [reload]);

  function toggleSlot(value: string) {
    setSlots((cur) => (cur.includes(value) ? cur.filter((s) => s !== value) : [...cur, value]));
  }

  function resetForm() {
    setName("");
    setSlots([]);
    setEditingId(null);
  }

  async function submit() {
    setError(null);
    if (!name.trim() || slots.length === 0) {
      setError("請填藥名並至少選一個時段");
      return;
    }
    try {
      if (editingId) {
        await updateMedication(elderId, editingId, name.trim(), slots);
      } else {
        await addMedication(elderId, name.trim(), slots);
      }
      resetForm();
      reload();
    } catch {
      setError("儲存失敗，請稍後再試");
    }
  }

  function startEdit(med: Medication) {
    setEditingId(med.medication_id);
    setName(med.name);
    setSlots(med.slots);
  }

  async function remove(medicationId: string) {
    try {
      await deleteMedication(elderId, medicationId);
      reload();
    } catch {
      setError("刪除失敗，請稍後再試");
    }
  }

  if (!meds) return <p>載入中…</p>;
  return (
    <main>
      <p>
        <Link to="/">← 返回長輩清單</Link>
      </p>
      <h1>用藥管理</h1>
      {error && <p>{error}</p>}
      <ul>
        {meds.map((m) => (
          <li key={m.medication_id}>
            {m.name}（{m.slots.map(slotLabel).join("、")}）
            <button type="button" onClick={() => startEdit(m)}>
              編輯
            </button>
            <button type="button" onClick={() => remove(m.medication_id)}>
              刪除
            </button>
          </li>
        ))}
      </ul>
      <h2>{editingId ? "編輯用藥" : "新增用藥"}</h2>
      <input value={name} onChange={(e) => setName(e.target.value)} placeholder="藥名" />
      <div>
        {SLOTS.map((s) => (
          <label key={s.value}>
            <input
              type="checkbox"
              checked={slots.includes(s.value)}
              onChange={() => toggleSlot(s.value)}
            />
            {s.label}
          </label>
        ))}
      </div>
      <button type="button" onClick={submit}>
        {editingId ? "更新" : "新增"}
      </button>
      {editingId && (
        <button type="button" onClick={resetForm}>
          取消編輯
        </button>
      )}
    </main>
  );
}
