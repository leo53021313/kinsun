import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  type Appointment,
  addAppointment,
  deleteAppointment,
  listAppointments,
  updateAppointment,
} from "../api";

const TODAY = new Date().toISOString().slice(0, 10);

export function AppointmentsPage() {
  const { elderId = "" } = useParams();
  const [appts, setAppts] = useState<Appointment[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [date, setDate] = useState("");
  const [label, setLabel] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);

  const reload = useCallback(() => {
    listAppointments(elderId)
      .then(setAppts)
      .catch(() => setError("載入失敗，請稍後再試"));
  }, [elderId]);

  useEffect(reload, [reload]);

  function resetForm() {
    setDate("");
    setLabel("");
    setEditingId(null);
  }

  async function submit() {
    setError(null);
    if (!date || !label.trim()) {
      setError("請填日期與內容");
      return;
    }
    try {
      if (editingId) {
        await updateAppointment(elderId, editingId, date, label.trim());
      } else {
        await addAppointment(elderId, date, label.trim());
      }
      resetForm();
      reload();
    } catch {
      setError("儲存失敗，請稍後再試");
    }
  }

  function startEdit(appt: Appointment) {
    setEditingId(appt.appointment_id);
    setDate(appt.date);
    setLabel(appt.label);
  }

  async function remove(appointmentId: string) {
    try {
      await deleteAppointment(elderId, appointmentId);
      reload();
    } catch {
      setError("刪除失敗，請稍後再試");
    }
  }

  if (!appts) return <p>載入中…</p>;
  return (
    <main>
      <p>
        <Link to="/">← 返回長輩清單</Link>
      </p>
      <h1>回診管理</h1>
      {error && <p>{error}</p>}
      <ul>
        {appts.map((a) => (
          <li key={a.appointment_id}>
            {a.date} {a.label}
            <button type="button" onClick={() => startEdit(a)}>
              編輯
            </button>
            <button type="button" onClick={() => remove(a.appointment_id)}>
              刪除
            </button>
          </li>
        ))}
      </ul>
      <h2>{editingId ? "編輯回診" : "新增回診"}</h2>
      <input type="date" min={TODAY} value={date} onChange={(e) => setDate(e.target.value)} />
      <input
        value={label}
        onChange={(e) => setLabel(e.target.value)}
        placeholder="例：上午10點 心臟科回診 林口長庚"
      />
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
