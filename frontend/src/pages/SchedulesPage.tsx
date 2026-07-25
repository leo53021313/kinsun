import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router";

import {
  type ScheduleGroup,
  addSchedule,
  deleteSchedule,
  listSchedules,
  updateSchedule,
} from "../api";
import { KIND_OPTIONS, SLOTS, describeGroup, toOccurrences } from "../schedules";
import { strings } from "../strings";

/**
 * 行程管理（D-76 P3）：用藥、回診與長輩自訂提醒共用一頁，取代原本的兩頁。
 *
 * 組請求的規則放在 ../schedules（純函式、可測），這裡只管畫面與狀態。
 */
export function SchedulesPage() {
  const { elderId = "" } = useParams();
  const [groups, setGroups] = useState<ScheduleGroup[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [kind, setKind] = useState<ScheduleGroup["kind"]>("medication");
  const [title, setTitle] = useState("");
  const [slots, setSlots] = useState<string[]>([]);
  const [when, setWhen] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);

  const reload = useCallback(() => {
    listSchedules(elderId)
      .then(setGroups)
      .catch(() => setError(strings.common.loadFailed));
  }, [elderId]);

  useEffect(reload, [reload]);

  function toggleSlot(value: string) {
    setSlots((cur) => (cur.includes(value) ? cur.filter((s) => s !== value) : [...cur, value]));
  }

  function resetForm() {
    setTitle("");
    setSlots([]);
    setWhen("");
    setEditingId(null);
  }

  async function submit() {
    const trimmed = title.trim();
    if (!trimmed) {
      setError(strings.schedules.titleRequired);
      return;
    }
    const built = toOccurrences(kind, { slots, when });
    if (!built) {
      setError(strings.schedules.whenRequired);
      return;
    }
    setError(null);
    const body = { kind, title: trimmed, ...built };
    try {
      if (editingId) {
        await updateSchedule(elderId, editingId, body);
      } else {
        await addSchedule(elderId, body);
      }
      resetForm();
      reload();
    } catch {
      setError(strings.common.saveFailed);
    }
  }

  function startEdit(group: ScheduleGroup) {
    setEditingId(group.group_id);
    setKind(group.kind);
    setTitle(group.title);
    setSlots([]);
    setWhen("");
    setError(strings.schedules.editHint);
  }

  async function remove(group: ScheduleGroup) {
    try {
      await deleteSchedule(elderId, group.group_id);
      if (editingId === group.group_id) {
        resetForm();
      }
      reload();
    } catch {
      setError(strings.common.deleteFailed);
    }
  }

  return (
    <main>
      <Link to="/elders">{strings.common.backToElders}</Link>
      <h1>{strings.schedules.title}</h1>
      {error ? <p role="alert">{error}</p> : null}

      {groups === null ? (
        <p>{strings.common.loading}</p>
      ) : groups.length === 0 ? (
        <p>{strings.schedules.empty}</p>
      ) : (
        <ul>
          {groups.map((g) => (
            <li key={g.group_id}>
              {describeGroup(g)}
              {/* 長輩自己用說的建的也在這一頁，標出來家屬才知道不是自己設的。 */}
              {g.created_by === "elder" ? <span> {strings.schedules.byElder}</span> : null}
              <button type="button" onClick={() => startEdit(g)}>
                {strings.common.edit}
              </button>
              <button type="button" onClick={() => remove(g)}>
                {strings.common.delete}
              </button>
            </li>
          ))}
        </ul>
      )}

      <h2>{editingId ? strings.schedules.editHeading : strings.schedules.addHeading}</h2>

      <fieldset>
        <legend>{strings.schedules.kindLabel}</legend>
        {KIND_OPTIONS.map((option) => (
          <label key={option.value}>
            <input
              type="radio"
              name="kind"
              checked={kind === option.value}
              onChange={() => setKind(option.value)}
            />
            {option.label}
          </label>
        ))}
      </fieldset>

      <label>
        {strings.schedules.titleLabel}
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder={strings.schedules.titlePlaceholder(kind)}
        />
      </label>

      {kind === "medication" ? (
        <>
          <fieldset>
            <legend>{strings.schedules.slotsLabel}</legend>
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
          </fieldset>
          <label>
            {strings.schedules.customTimeLabel}
            <input value={when} onChange={(e) => setWhen(e.target.value)} placeholder="07:30" />
          </label>
        </>
      ) : (
        <label>
          {strings.schedules.whenLabel(kind)}
          <input
            value={when}
            onChange={(e) => setWhen(e.target.value)}
            placeholder={strings.schedules.whenPlaceholder(kind)}
          />
        </label>
      )}

      <button type="button" onClick={submit}>
        {editingId ? strings.common.update : strings.common.add}
      </button>
      {editingId ? (
        <button type="button" onClick={resetForm}>
          {strings.common.cancelEdit}
        </button>
      ) : null}
    </main>
  );
}
