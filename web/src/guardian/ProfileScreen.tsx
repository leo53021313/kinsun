/** 「我的」分頁（W5a）。長輩帳密與邀請功能仍在既有詳情頁，從本頁進去。 */

import type { Elder } from "kinsun-shared/types";

import { strings } from "@/strings";

import { primaryElderLabel, useGuardianTabsState } from "./guardianTabsContext";
import { TabLanding } from "./TabLanding";

export function ProfileScreen(props: {
  onOpenElder: (elder: Elder) => void;
  onAddElder: () => void;
}) {
  const { primaryElder } = useGuardianTabsState();
  return (
    <TabLanding
      // 標題就是這位長輩的稱呼——設計稿的這一項本來就是長輩的名字，不是「我的」。
      title={primaryElderLabel(primaryElder)}
      actionLabel={strings.elderDetail.openDetail}
      onOpenElder={props.onOpenElder}
      onAddElder={props.onAddElder}
    />
  );
}
