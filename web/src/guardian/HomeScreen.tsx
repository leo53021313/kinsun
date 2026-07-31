import { useEffect, useMemo, useState } from "react";

import { emitStageEvent } from "@/notify/bus";
import { GuardianSession } from "@/session/contexts";
import { makeSignOutOnAuthError } from "@/session/useSignOutOnAuthError";
import { strings } from "@/strings";
import { Button } from "@/ui/Button";
import { EmptyHint, ErrorText } from "@/ui/Feedback";
import { Field } from "@/ui/Field";
import { Section } from "@/ui/Section";
import type { Elder } from "kinsun-shared/types";

import { createElder, listElders, logoutGuardian } from "./api";
import { InviteCard } from "./InviteCard";

export function HomeScreen(props: {
  onOpenElder: (elderId: string, elderName: string) => void;
  onOpenNotifications: () => void;
  /**
   * 把剛拿到的綁定碼直接送到長輩欄（spec W-15 內測捷徑，接線見
   * `stage/StagePage.tsx`）。不傳的話 `InviteCard` 不畫出「送到長輩的手機」鈕
   * （見該元件 `onSendToElder` 的說明）——獨立測試這支畫面（不透過
   * `StagePage`）時沒有另一欄可以送，這顆按鈕不該出現。
   */
  onSendCodeToElder?: (code: string) => void;
}) {
  const { session, signOut } = GuardianSession.useSession();
  const token = session?.token ?? "";
  // ⚠️ null＝還沒載完、[]＝真的一位長輩都沒有。兩者不可共用同一個值：初始就給 []
  // 的話，載入途中畫面會顯示「還沒有長輩檔案，先在上面建立一位吧」——見下面
  // hasError 的說明，那句話會誘導家屬建出刪不掉的重複長輩。
  const [elders, setElders] = useState<Elder[] | null>(null);
  const [newName, setNewName] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  // ⚠️ 布林旗標、與下面表單的 formError 分開：列表載入失敗**必須取代**空狀態，
  // 不可與「還沒有長輩檔案，先在上面建立一位吧」同框（沿用 NotificationsScreen
  // 與 ElderDetailScreen 三個區塊旗標的同一種寫法）。
  //
  // 失效路徑：家屬已有兩位長輩 → 後端短暫 500 或通道抖一下 → 首頁說「還沒有長輩
  // 檔案」→ 他照著輸入「阿公」按建立 → 後端恢復 → 建出第三筆重複的長輩檔案。
  // 後端**沒有 DELETE /elders**，這筆重複資料從 web 端與 App 端都刪不掉。
  const [hasError, setHasError] = useState(false);
  // 只屬於「新增長輩」表單的錯誤（沒填稱呼、建立失敗），故留在該 Section 內部；
  // 列表的載入失敗走上面的 hasError、畫在列表的位置——兩者混用同一個字串狀態時，
  // 「載入失敗」會黏在建立表單下方，讀起來像「建立失敗」，但失敗的其實是列表。
  const [formError, setFormError] = useState("");
  const [busy, setBusy] = useState(false);
  // 登出也要防連按：`Button` 早就有這個能力（註解還寫明「家屬連按兩下『建立長輩
  // 檔案』會建出兩位長輩」），登出這顆先前沒接上——連按兩下會送出兩次撤銷 token
  // 的請求，第二次必然吃 401。不需要在結束時歸零：`signOut()` 之後這個畫面就被
  // `GuardianApp` 換掉了。
  const [logoutBusy, setLogoutBusy] = useState(false);

  // makeSignOutOnAuthError 是工廠、回傳的是函式值，所以用 useMemo 而非 useCallback
  // （useCallback 收的應該是行內函式表達式，react-hooks 規則會擋）。signOut 在
  // session 工廠裡是 useCallback([]) 的穩定參考，所以這個值也穩定，不會讓下面的
  // effect 反覆重打 API。
  const signOutOn401 = useMemo(() => makeSignOutOnAuthError(signOut), [signOut]);

  useEffect(() => {
    if (!token) {
      return;
    }
    let alive = true;
    listElders(token)
      .then((list) => {
        if (alive) setElders(list);
      })
      .catch((exc) => {
        if (signOutOn401(exc)) return;
        if (alive) setHasError(true);
      });
    return () => {
      alive = false;
    };
  }, [token, signOutOn401]);

  async function addElder() {
    const name = newName.trim();
    if (!name) {
      setFormError(strings.guardianHome.nameRequired);
      return;
    }
    setFormError("");
    setBusy(true);
    try {
      const created = await createElder(name, token);
      // ⚠️ 帶上 nickname：後端一直都有回它，App 版曾經在這裡把它丟掉，於是剛新增
      // 的那一筆在列表上少一個稱謂、要重新整理才會出現（A-10）。
      // `prev ?? []`：列表還沒載完（null）時家屬就按了建立，展開 null 會直接炸掉。
      setElders((prev) => [
        ...(prev ?? []),
        { elder_id: created.elder_id, name: created.name, nickname: created.nickname },
      ]);
      setInviteCode(created.invite_code);
      setNewName("");
      // 讓長輩欄立刻去拉，不必等下一次輪詢（見 notify/bus 的說明）。
      emitStageEvent("guardian-wrote");
      // ⚠️ 建立成功後重打一次列表。上面那筆樂觀追加只夠應付「列表本來就載到了」
      // 的情形；若這一頁是帶著 hasError 進來的，錯誤訊息會佔住清單的位置、把剛
      // 建好的那位蓋掉，而且清單其實還少了家屬原有的其他長輩——他會以為建立失敗
      // 而再按一次，重新走回「建出刪不掉的重複長輩」那條路。
      // 建立成功代表後端此刻是通的，這一趟通常會成功。
      try {
        setElders(await listElders(token));
        setHasError(false);
      } catch (reloadExc) {
        if (signOutOn401(reloadExc)) return;
        // 重打失敗不影響「建立成功」這件事本身（綁定碼已經顯示出來了）。清單維持
        // 原狀、錯誤旗標也維持原狀——不謊稱這份清單是完整的。
      }
    } catch (exc) {
      if (signOutOn401(exc)) return;
      setFormError(strings.guardianHome.addFailed);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-ink">{strings.guardianHome.title}</h1>
        <button
          type="button"
          onClick={props.onOpenNotifications}
          className="min-h-12 rounded-xl border border-line bg-surface px-4 text-sm font-semibold text-ink"
        >
          {strings.guardianHome.notify}
        </button>
      </div>

      <Section title={strings.guardianHome.addElderSection}>
        <Field
          label={strings.guardianHome.elderNameLabel}
          value={newName}
          onChange={setNewName}
          placeholder={strings.guardianHome.elderNamePlaceholder}
        />
        <p className="text-xs leading-5 text-ink-soft">{strings.guardianHome.consent}</p>
        <Button label={strings.guardianHome.createElder} onClick={addElder} busy={busy} />
        {inviteCode ? (
          <InviteCard
            code={inviteCode}
            onSendToElder={
              props.onSendCodeToElder ? () => props.onSendCodeToElder?.(inviteCode) : undefined
            }
          />
        ) : null}
        <ErrorText message={formError} />
      </Section>

      {/* 順序固定為 錯誤 → 載入中 → 空狀態 → 清單（與 NotificationsScreen 一致）：
          任何一種「還沒有資料」的情形都不得落到空狀態那句引導文字上。 */}
      {hasError ? (
        <ErrorText message={strings.common.loadFailed} />
      ) : elders === null ? (
        <EmptyHint text={strings.common.loading} />
      ) : elders.length === 0 ? (
        <EmptyHint text={strings.guardianHome.empty} />
      ) : (
        <ul className="flex flex-col gap-2">
          {elders.map((elder) => (
            <li key={elder.elder_id}>
              <button
                type="button"
                onClick={() => props.onOpenElder(elder.elder_id, elder.name)}
                className="flex min-h-14 w-full items-center justify-between rounded-2xl border border-line bg-surface px-4 text-left"
              >
                <span className="text-base font-bold text-ink">{elder.name}</span>
                <span aria-hidden className="text-xl text-ink-soft">
                  ›
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      <Button
        label={strings.guardianHome.logout}
        variant="outline"
        busy={logoutBusy}
        onClick={async () => {
          setLogoutBusy(true);
          await logoutGuardian(token).catch(() => undefined);
          signOut();
        }}
      />
    </div>
  );
}
