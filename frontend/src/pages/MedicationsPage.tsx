import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router";

import {
  type Medication,
  addMedication,
  deleteMedication,
  listMedications,
  updateMedication,
} from "../api";
import { SLOTS, slotLabel } from "../medicationSlots";
import { strings } from "../strings";

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
      .catch(() => setError(strings.common.loadFailed));
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
      setError(strings.medications.slotRequired);
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
      setError(strings.common.saveFailed);
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
      setError(strings.common.deleteFailed);
    }
  }

  if (!meds) return <p>{strings.common.loading}</p>;
  return (
    <main>
      <p>
        <Link to="/">{strings.common.backToElders}</Link>
      </p>
      <h1>{strings.medications.title}</h1>
      {error && <p>{error}</p>}
      <ul>
        {meds.map((m) => (
          <li key={m.medication_id}>
            {m.name}（{m.slots.map(slotLabel).join("、")}）
            <button type="button" onClick={() => startEdit(m)}>
              {strings.common.edit}
            </button>
            <button type="button" onClick={() => remove(m.medication_id)}>
              {strings.common.delete}
            </button>
          </li>
        ))}
      </ul>
      <h2>{editingId ? strings.medications.editHeading : strings.medications.addHeading}</h2>
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder={strings.medications.namePlaceholder}
      />
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
        {editingId ? strings.common.update : strings.common.add}
      </button>
      {editingId && (
        <button type="button" onClick={resetForm}>
          {strings.common.cancelEdit}
        </button>
      )}
    </main>
  );
}
