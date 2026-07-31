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

import { apiErrorMessage } from "@/api";
import { emitStageEvent } from "@/notify/bus";
import { GuardianSession } from "@/session/contexts";
import { makeSignOutOnAuthError } from "@/session/useSignOutOnAuthError";
import { strings } from "@/strings";
import { Button } from "@/ui/Button";
import { EmptyHint, ErrorText, NoticeText } from "@/ui/Feedback";
import { Field } from "@/ui/Field";
import { Section } from "@/ui/Section";

import { createSchedule, deleteSchedule, listSchedules, updateSchedule } from "./api";
import { KIND_OPTIONS, SLOTS, describeGroup, toOccurrences } from "./schedules";

type Kind = ScheduleGroup["kind"];

export function SchedulesScreen(props: { elderId: string; elderName: string }) {
  const { elderId, elderName } = props;
  const { session, signOut } = GuardianSession.useSession();
  const token = session?.token ?? "";
  // ⚠️ 用 useMemo 而非 useCallback：makeSignOutOnAuthError 是**工廠**，回傳的是函式
  // 值，而 useCallback 收的應該是行內函式表達式——react-hooks 的規則會擋下來。
  // signOut 在 session 工廠裡是 useCallback([]) 的穩定參考，所以這個值也穩定，
  // 不會讓下面的 effect 反覆重打 API。
  const signOutOn401 = useMemo(() => makeSignOutOnAuthError(signOut), [signOut]);

  const [groups, setGroups] = useState<ScheduleGroup[] | null>(null);
  // ⚠️ 清單載入失敗用獨立的布林旗標、不共用下面那個 error 字串：`groups` 留在 null
  // 時畫面會照樣顯示「載入中…」，於是錯誤與載入中兩句互相矛盾的話同時出現，家屬
  // 會照著「載入中」等下去——而且永遠等不到（沒有重試鈕，唯一復原方式是返回再進
  // 來）。同一份清單在 ElderDetailScreen 早就是用 groupsError 降級的，此處對齊。
  const [groupsError, setGroupsError] = useState(false);
  const [kind, setKind] = useState<Kind>("medication");
  const [title, setTitle] = useState("");
  const [slots, setSlots] = useState<string[]>([]);
  const [when, setWhen] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<ScheduleGroup | null>(null);
  const [error, setError] = useState("");
  // ⚠️ 與 error 分開：「修改後請重新填一次提醒時間。」是按下「編輯」之後的**操作
  // 指示**，不是錯誤。走 ErrorText 的話畫面會對一個成功的操作跳紅字，螢幕報讀
  // 軟體還會把它當警示朗讀（Feedback.tsx 檔頭寫明該元件是給錯誤與空狀態用的）。
  const [hint, setHint] = useState("");
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
      setGroupsError(false);
    } catch (exc) {
      if (signOutOn401(exc)) return;
      // ⚠️ 這一路走頁面最上方的 error、不設 groupsError：重打是寫入成功之後的事，
      // `groups` 還留著上一份清單。設旗標會把那份還看得到的資料換成錯誤字，家屬
      // 反而失去手上僅有的資訊；「寫進去了、清單沒刷新」照實說即可。
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
        if (alive) setGroupsError(true);
      });
    return () => {
      alive = false;
    };
  }, [elderId, token, signOutOn401]);

  // 按下「編輯」進來的提示（「修改後請重新填一次提醒時間。」）若不在這裡一併
  // 清掉，按「取消編輯」回到新增模式後那句提示會留在畫面上，跟眼前空白的表單對
  // 不上——家屬會以為剛才什麼操作出錯了。
  function resetForm() {
    setTitle("");
    setSlots([]);
    setWhen("");
    setEditingId(null);
    setError("");
    setHint("");
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
    // 送出時先收掉「請重新填一次時間」那句指示：它已經被照做（或被無視）了，
    // 留著會跟下面可能出現的格式錯誤訊息疊在一起講同一件事。
    setHint("");
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
      // 讓長輩欄立刻去拉，不必等下一次輪詢（見 notify/bus 的說明）。
      emitStageEvent("guardian-wrote");
      await reload();
    } catch (exc) {
      if (signOutOn401(exc)) return;
      // 後端的排程驗證訊息是寫給人看的繁中句子（A-01），直接顯示；
      // ⚠️ apiErrorMessage 多擋一層：後端回應不是合法 JSON 時 exc.message 會是
      // shared/client.ts 自造的英文字面值（如 `HTTP 502`），一律退回 saveFailed。
      setError(apiErrorMessage(exc, strings.common.saveFailed));
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
      // 讓長輩欄立刻去拉，不必等下一次輪詢（見 notify/bus 的說明）。
      emitStageEvent("guardian-wrote");
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
      <h1 className="text-lg font-bold text-ink">{strings.schedules.title(elderName)}</h1>
      <ErrorText message={error} />
      <NoticeText message={hint} />

      <Section title={strings.schedules.listSection}>
        {/* 順序固定為 錯誤 → 載入中 → 空狀態 → 清單（與 ElderDetailScreen 一致）。 */}
        {groupsError ? (
          <ErrorText message={strings.common.loadFailed} />
        ) : groups === null ? (
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
                    setError("");
                    setHint(strings.schedules.editHint);
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
