import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router";

import {
  type Appointment,
  addAppointment,
  deleteAppointment,
  listAppointments,
  updateAppointment,
} from "../api";
import { strings } from "../strings";

const TODAY = new Date().toISOString().slice(0, 10);

export function AppointmentsPage() {
  const { elderId = "" } = useParams();
  const [appts, setAppts] = useState<Appointment[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [label, setLabel] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);

  const reload = useCallback(() => {
    listAppointments(elderId)
      .then(setAppts)
      .catch(() => setError(strings.common.loadFailed));
  }, [elderId]);

  useEffect(reload, [reload]);

  function resetForm() {
    setDate("");
    setTime("");
    setLabel("");
    setEditingId(null);
  }

  async function submit() {
    setError(null);
    if (!date || !label.trim()) {
      setError(strings.appointments.fieldsRequired);
      return;
    }
    try {
      if (editingId) {
        await updateAppointment(elderId, editingId, date, label.trim(), time);
      } else {
        await addAppointment(elderId, date, label.trim(), time);
      }
      resetForm();
      reload();
    } catch {
      setError(strings.common.saveFailed);
    }
  }

  function startEdit(appt: Appointment) {
    setEditingId(appt.appointment_id);
    setDate(appt.date);
    setTime(appt.time);
    setLabel(appt.label);
  }

  async function remove(appointmentId: string) {
    try {
      await deleteAppointment(elderId, appointmentId);
      reload();
    } catch {
      setError(strings.common.deleteFailed);
    }
  }

  if (!appts) return <p>{strings.common.loading}</p>;
  return (
    <main>
      <p>
        <Link to="/">{strings.common.backToElders}</Link>
      </p>
      <h1>{strings.appointments.title}</h1>
      {error && <p>{error}</p>}
      <ul>
        {appts.map((a) => (
          <li key={a.appointment_id}>
            {a.date}
            {a.time ? ` ${a.time}` : ""} {a.label}
            <button type="button" onClick={() => startEdit(a)}>
              {strings.common.edit}
            </button>
            <button type="button" onClick={() => remove(a.appointment_id)}>
              {strings.common.delete}
            </button>
          </li>
        ))}
      </ul>
      <h2>{editingId ? strings.appointments.editHeading : strings.appointments.addHeading}</h2>
      <input type="date" min={TODAY} value={date} onChange={(e) => setDate(e.target.value)} />
      <input
        type="time"
        value={time}
        onChange={(e) => setTime(e.target.value)}
        title={strings.appointments.timeTitle}
      />
      <input
        value={label}
        onChange={(e) => setLabel(e.target.value)}
        placeholder={strings.appointments.labelPlaceholder}
      />
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
