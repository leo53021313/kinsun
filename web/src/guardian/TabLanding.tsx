/**
 * 「報告」與「我的」兩個分頁的落地頁（W5a）。
 *
 * ⚠️ **它刻意很薄。** 完整的健康報告、長輩帳密與邀請功能都還在既有的長輩詳情頁；
 * 這一頁只負責「認出目前這位長輩，然後把人帶進去」。App 那側是同一個形狀
 * （`app/src/components/GuardianTabLanding.tsx`，report／profile 各 12 行），web 照搬
 * 是為了不製造新的兩端分岔——要讓這兩頁變厚是設計決定，兩端要一起做。
 *
 * ⚠️ 導覽以 props 傳進來而不是自己呼叫 router：W5a 不動 `GuardianApp` 的路由結構，
 * 這兩頁因此可以獨立完成、獨立測試，把風險留給 W5b 的導覽改造。
 */

import type { Elder } from "kinsun-shared/types";

import { strings } from "@/strings";
import { Button } from "@/ui/Button";
import { EmptyHint, ErrorText } from "@/ui/Feedback";
import { Section } from "@/ui/Section";

import { useGuardianTabsState } from "./guardianTabsContext";

export function TabLanding(props: {
  title: string;
  /** 進長輩詳情那顆鈕的字，兩個分頁各自不同（報告／長輩詳情）。 */
  actionLabel: string;
  onOpenElder: (elder: Elder) => void;
  /** 還沒有長輩時，把人帶回首頁去建立。 */
  onAddElder: () => void;
}) {
  const { primaryElder, loaded, error, refreshPrimaryElder } = useGuardianTabsState();
  const elderName = primaryElder?.nickname?.trim() || primaryElder?.name?.trim() || "";

  return (
    <div className="flex h-full flex-col gap-3 p-4">
      <Section title={props.title}>
        {!loaded ? <EmptyHint text={strings.common.loading} /> : null}
        <ErrorText message={error} />

        {loaded && !error && !primaryElder ? (
          <>
            <EmptyHint text={strings.guardianHome.empty} />
            <Button label={strings.guardianHome.addElderSection} onClick={props.onAddElder} />
          </>
        ) : null}

        {primaryElder ? (
          <>
            <p className="text-elder-min font-extrabold text-ink">{elderName}</p>
            <Button
              label={props.actionLabel}
              onClick={() => props.onOpenElder(primaryElder)}
            />
          </>
        ) : null}

        {error ? (
          <Button
            label={strings.common.retry}
            variant="subtle"
            onClick={() => void refreshPrimaryElder()}
          />
        ) : null}
      </Section>
    </div>
  );
}
