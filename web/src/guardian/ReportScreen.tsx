/** 「報告」分頁（W5a）。完整報告內容沿用既有長輩詳情，從本頁進去。 */

import type { Elder } from "kinsun-shared/types";

import { strings } from "@/strings";

import { TabLanding } from "./TabLanding";

export function ReportScreen(props: {
  onOpenElder: (elder: Elder) => void;
  onAddElder: () => void;
}) {
  return (
    <TabLanding
      title={strings.guardianTabs.report}
      actionLabel={strings.elderDetail.healthReportSection}
      onOpenElder={props.onOpenElder}
      onAddElder={props.onAddElder}
    />
  );
}
