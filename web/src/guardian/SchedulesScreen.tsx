/**
 * 行程管理（D-76 P3）：用藥、回診與長輩自訂共用一頁。
 *
 * 三種類型問的問題不同，所以「時間」欄位隨類型換輸入方式：用藥選時段（或直接打
 * 時刻）、回診填日期、其他填重複方式。組請求的邏輯全在 ./schedules.ts，這裡只管畫面。
 *
 * ⚠️ 刪除用畫面內的確認列而非瀏覽器的 confirm()：confirm 會鎖住整個分頁，
 * 左欄的長輩端連對講機都按不了——雙欄同時存在時，任何 modal 對話框都是全域的。
 */

import type { ScheduleGroup, ScheduleInput } from "kinsun-shared/types";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";

import { ApiError } from "@/api";
import { GuardianSession } from "@/session/contexts";
import { makeSignOutOnAuthError } from "@/session/useSignOutOnAuthError";
import { strings } from "@/strings";
import { Button } from "@/ui/Button";
import { EmptyHint, ErrorText } from "@/ui/Feedback";
import { Field } from "@/ui/Field";
import { Section } from "@/ui/Section";

import { createSchedule, deleteSchedule, listSchedules, updateSchedule } from "./api";
import { KIND_OPTIONS, SLOTS, describeGroup, toOccurrences } from "./schedules";

type Kind = ScheduleGroup["kind"];

export function SchedulesScreen(props: { elderId: string }) {
  const { elderId } = props;
  const { session, signOut } = GuardianSession.useSession();
  const token = session?.token ?? "";
  // ⚠️ 用 useMemo 而非 useCallback：makeSignOutOnAuthError 是**工廠**，回傳的是函式
  // 值，而 useCallback 收的應該是行內函式表達式——react-hooks 的規則會擋下來。
  // signOut 在 session 工廠裡是 useCallback([]) 的穩定參考，所以這個值也穩定，
  // 不會讓下面的 effect 反覆重打 API。
  const signOutOn401 = useMemo(() => makeSignOutOnAuthError(signOut), [signOut]);

  const [groups, setGroups] = useState<ScheduleGroup[] | null>(null);
  const [kind, setKind] = useState<Kind>("medication");
  const [title, setTitle] = useState("");
  const [slots, setSlots] = useState<string[]>([]);
  const [when, setWhen] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<ScheduleGroup | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // 刪除確認列（role="alertdialog"）：出現時要把焦點移進去，讀螢幕的人才聽得到
  // 「確定要刪除…」這句話——它在 DOM 裡但焦點沒過去，螢幕報讀軟體不會朗讀它。
  const confirmHeadingId = useId();
  const confirmDialogRef = useRef<HTMLDivElement | null>(null);

  // 這支給送出（新增／修改／刪除）之後手動呼叫，用來重打清單；不是給下面的初次
  // 載入 effect 用——effect 裡直接呼叫這支 useCallback 出來的非同步函式會被
  // react-hooks/set-state-in-effect 判定為「在 effect 裡呼叫會 setState 的函式」
  // 而擋下來，即使它是非同步的。初次載入改用與 HomeScreen／ElderDetailScreen
  // 一致的寫法：effect 內直接 `.then()／.catch()`，並用 `alive` 防止卸載後還寫入。
  const reload = useCallback(async () => {
    if (!token) return;
    try {
      setGroups(await listSchedules(elderId, token));
    } catch (exc) {
      if (signOutOn401(exc)) return;
      setError(strings.common.loadFailed);
    }
  }, [elderId, token, signOutOn401]);

  useEffect(() => {
    if (!token) return;
    let alive = true;
    listSchedules(elderId, token)
      .then((list) => {
        if (alive) setGroups(list);
      })
      .catch((exc) => {
        if (signOutOn401(exc)) return;
        if (alive) setError(strings.common.loadFailed);
      });
    return () => {
      alive = false;
    };
  }, [elderId, token, signOutOn401]);

  // 按下「編輯」進來的紅字提示（「修改後請重新填一次提醒時間。」）若不在這裡一併
  // 清掉，按「取消編輯」回到新增模式後那句提示會留在畫面上，跟眼前空白的表單對
  // 不上——家屬會以為剛才什麼操作出錯了。
  function resetForm() {
    setTitle("");
    setSlots([]);
    setWhen("");
    setEditingId(null);
    setError("");
  }

  // 確認列一出現就把焦點移進去（見上面 confirmDialogRef 的說明）。
  useEffect(() => {
    if (pendingDelete) {
      confirmDialogRef.current?.focus();
    }
  }, [pendingDelete]);

  function buildBody(): ScheduleInput | null {
    const trimmed = title.trim();
    if (!trimmed) return null;
    const built = toOccurrences(kind, { slots, when });
    return built ? { kind, title: trimmed, ...built } : null;
  }

  async function submit() {
    const body = buildBody();
    if (!body) {
      setError(strings.schedules.whenRequired);
      return;
    }
    setError("");
    setBusy(true);
    try {
      if (editingId) {
        await updateSchedule(elderId, editingId, body, token);
      } else {
        await createSchedule(elderId, body, token);
      }
      resetForm();
      await reload();
    } catch (exc) {
      if (signOutOn401(exc)) return;
      // 後端的排程驗證訊息是寫給人看的繁中句子（A-01），直接顯示。
      setError(exc instanceof ApiError ? exc.message : strings.common.saveFailed);
    } finally {
      setBusy(false);
    }
  }

  async function confirmDelete() {
    const group = pendingDelete;
    if (!group) return;
    setBusy(true);
    try {
      await deleteSchedule(elderId, group.group_id, token);
      if (editingId === group.group_id) resetForm();
      setPendingDelete(null);
      await reload();
    } catch (exc) {
      if (signOutOn401(exc)) return;
      setError(strings.common.deleteFailed);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4">
      <h1 className="text-lg font-bold text-ink">{strings.schedules.title}</h1>
      <ErrorText message={error} />

      <Section title={strings.schedules.listSection}>
        {groups === null ? (
          <EmptyHint text={strings.common.loading} />
        ) : groups.length === 0 ? (
          <EmptyHint text={strings.schedules.empty} />
        ) : (
          groups.map((group) => (
            <div key={group.group_id} className="flex flex-col gap-1 border-b border-line pb-2 last:border-0">
              <span className="text-sm text-ink">{describeGroup(group)}</span>
              {group.created_by === "elder" ? (
                <span className="text-xs text-ink-soft">{strings.schedules.byElder}</span>
              ) : null}
              <div className="flex gap-2">
                <Button
                  label={strings.common.edit}
                  variant="outline"
                  disabled={busy}
                  onClick={() => {
                    setEditingId(group.group_id);
                    setKind(group.kind);
                    setTitle(group.title);
                    setSlots([]);
                    setWhen("");
                    // ⚠️ 這裡原本寫「後端回的是算好的鬧鐘，反推不回去」，是錯的根因：
                    // daily／weekly／once 都可以無損反推——describeGroup 排出來的字串
                    // （如「每週三 15:00」）本身就是 customOccurrences 吃得下的輸入格式，
                    // 兩者互為映射，沒有資訊被丟掉。
                    //
                    // 真正有損的只有用藥的「時段勾選」：occurrences 只存得住展開後的
                    // 時刻（如 08:00），存不住當初是「勾了早上」還是「手動打 08:00」；
                    // slotLabelForTime 只能按時段區間反猜，猜錯或猜對都無法確認，而且
                    // 多選時段（如早上＋晚上）展開成多筆 occurrence 後也回不去勾選狀態。
                    //
                    // 因為三種類型共用同一支表單、同一套「時間留空＋提示重填」的規則
                    // 比替每種類型各寫一套精確反推邏輯單純得多，所以即使 daily／weekly／
                    // once 技術上可以做到無損回填，這裡仍統一請家屬重填一次。
                    setError(strings.schedules.editHint);
                  }}
                />
                <Button
                  label={strings.common.delete}
                  variant="outline"
                  disabled={busy}
                  onClick={() => setPendingDelete(group)}
                />
              </div>
            </div>
          ))
        )}
      </Section>

      {pendingDelete ? (
        <div
          ref={confirmDialogRef}
          tabIndex={-1}
          role="alertdialog"
          aria-modal="true"
          aria-labelledby={confirmHeadingId}
          className="flex flex-col gap-2 rounded-2xl border-2 border-danger bg-surface p-4"
        >
          <p id={confirmHeadingId} className="text-sm text-ink">
            {strings.schedules.confirmDelete(pendingDelete.title)}
          </p>
          <div className="flex gap-2">
            <Button label={strings.schedules.confirmDeleteButton} onClick={confirmDelete} busy={busy} />
            <Button
              label={strings.common.cancel}
              variant="outline"
              disabled={busy}
              onClick={() => setPendingDelete(null)}
            />
          </div>
        </div>
      ) : null}

      <Section title={editingId ? strings.schedules.editSection : strings.schedules.addSection}>
        <fieldset>
          <legend className="text-sm font-semibold text-ink-soft">{strings.schedules.kindLabel}</legend>
          <div role="radiogroup" aria-label={strings.schedules.kindLabel} className="mt-2 flex flex-wrap gap-2">
            {KIND_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                role="radio"
                aria-checked={kind === option.value}
                // 編輯模式下鎖住類型：中途改成別的類型再按更新，後端會因為新舊欄位對不
                // 上而回 400（訊息本身沒問題），但這一趟本可省下——編輯中本來就該先把
                // 現有那筆改完，要換類型就先取消編輯再新增一筆。
                disabled={editingId !== null}
                onClick={() => setKind(option.value)}
                className={`min-h-12 rounded-full border-2 px-4 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50 ${
                  kind === option.value
                    ? "border-primary bg-primary text-white"
                    : "border-line bg-surface text-ink"
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </fieldset>

        <Field
          label={strings.schedules.titleLabel}
          value={title}
          onChange={setTitle}
          placeholder={strings.schedules.titlePlaceholder(kind)}
        />

        {kind === "medication" ? (
          <>
            <fieldset>
              <legend className="text-sm font-semibold text-ink-soft">{strings.schedules.slotsLabel}</legend>
              <div className="mt-2 flex flex-wrap gap-2">
                {SLOTS.map((slot) => (
                  <button
                    key={slot.value}
                    type="button"
                    role="checkbox"
                    aria-checked={slots.includes(slot.value)}
                    onClick={() =>
                      setSlots((cur) =>
                        cur.includes(slot.value)
                          ? cur.filter((s) => s !== slot.value)
                          : [...cur, slot.value],
                      )
                    }
                    className={`min-h-12 rounded-full border-2 px-4 text-sm font-semibold ${
                      slots.includes(slot.value)
                        ? "border-primary bg-primary text-white"
                        : "border-line bg-surface text-ink"
                    }`}
                  >
                    {slot.label}
                  </button>
                ))}
              </div>
            </fieldset>
            <Field
              label={strings.schedules.customTimeLabel}
              value={when}
              onChange={setWhen}
              placeholder={strings.schedules.customTimePlaceholder}
            />
          </>
        ) : (
          <Field
            label={strings.schedules.whenLabel(kind)}
            value={when}
            onChange={setWhen}
            placeholder={strings.schedules.whenPlaceholder(kind)}
          />
        )}

        <Button
          label={editingId ? strings.common.update : strings.common.create}
          onClick={submit}
          busy={busy}
          disabled={!title.trim()}
        />
        {editingId ? (
          <Button label={strings.common.cancelEdit} variant="outline" onClick={resetForm} />
        ) : null}
      </Section>
    </div>
  );
}
