import { GuardianTabLanding } from "@/components/GuardianTabLanding";
import { strings } from "@/lib/strings";

/** 批次 5 先完成 tab 路由；長輩帳密與邀請功能仍在既有詳情頁。 */
export default function GuardianProfile() {
  return (
    <GuardianTabLanding
      title={strings.guardianTabs.profile}
      actionLabel={strings.nav.elderDetail}
    />
  );
}
