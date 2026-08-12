import { GuardianTabLanding } from "@/components/GuardianTabLanding";
import { strings } from "@/lib/strings";

/** 批次 5 先完成 tab 路由；完整報告內容沿用既有長輩詳情，從本頁 push 進去。 */
export default function GuardianReport() {
  return (
    <GuardianTabLanding
      title={strings.guardianTabs.report}
      actionLabel={strings.elderDetail.healthReportSection}
    />
  );
}
