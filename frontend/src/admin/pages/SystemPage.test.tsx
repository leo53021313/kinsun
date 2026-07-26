import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getMeta, getRagStatus, listJobs } from "../api";
import { SystemPage } from "./SystemPage";

vi.mock("../api", () => ({
  listJobs: vi.fn(),
  getRagStatus: vi.fn(),
  getMeta: vi.fn(),
  runJob: vi.fn(),
}));

const RAG = {
  active_release: null,
  active_published_at: null,
  latest_release: null,
  latest_status: null,
  document_count: 0,
  chunk_count: 0,
  content_policy: "allowed_only",
  warnings: [],
};

function job(overrides: Record<string, unknown> = {}) {
  return {
    job_name: "schedule-dispatch",
    cron: "* * * * *",
    owner: "scheduler",
    can_run_now: true,
    last_run_at: 1_785_000_000,
    due_at: 1_785_000_060,
    late_seconds: 0,
    is_overdue: false,
    never_ran: false,
    ...overrides,
  };
}

describe("SystemPage 排程健康狀態", () => {
  beforeEach(() => {
    vi.mocked(listJobs).mockReset();
    vi.mocked(getRagStatus).mockReset().mockResolvedValue(RAG as never);
    vi.mocked(getMeta).mockReset().mockResolvedValue({ internal_testing: false });
  });

  it("排程正常時不顯示任何告警", async () => {
    vi.mocked(listJobs).mockResolvedValue({
      jobs: [job()],
      meta: { overdue: [], never_ran: [], warnings: [] },
    } as never);

    render(<SystemPage />);

    expect(await screen.findByText("正常")).toBeInTheDocument();
    expect(screen.queryByText(/逾期/)).not.toBeInTheDocument();
  });

  it("逾期的 job 顯示遲到多久，並把後端告警置頂", async () => {
    // ⚠️ 這條守的是 2026-07-26 停擺事故最末端的一環：後端算出了逾期，
    // 但這一頁當時只印「上次執行」的時間戳，13 天沒跑也沒有任何提示。
    vi.mocked(listJobs).mockResolvedValue({
      jobs: [job({ is_overdue: true, late_seconds: 1_123_200 })],
      meta: {
        overdue: ["schedule-dispatch"],
        never_ran: [],
        warnings: ["有 1 支排程逾期未執行：schedule-dispatch（排程器可能沒在跑或已卡死）"],
      },
    } as never);

    render(<SystemPage />);

    expect(await screen.findByText(/逾期 13 天/)).toBeInTheDocument();
    expect(screen.getByText(/排程器可能沒在跑或已卡死/)).toBeInTheDocument();
  });

  it("從未執行的 job 標成異常，而不是顯示成健康", async () => {
    // 沒有 last_run_at 就算不出 due_at、is_overdue 恆為 false——
    // 若照 is_overdue 判色，一支從沒被排程器碰過的 job 會是全綠的。
    vi.mocked(listJobs).mockResolvedValue({
      jobs: [job({ last_run_at: null, due_at: null, never_ran: true })],
      meta: {
        overdue: [],
        never_ran: ["schedule-dispatch"],
        warnings: ["有 1 支排程從未執行過：schedule-dispatch"],
      },
    } as never);

    render(<SystemPage />);

    expect(await screen.findByText("⚠ 從未執行")).toBeInTheDocument();
    expect(screen.getByText(/從未執行過/)).toBeInTheDocument();
    expect(screen.queryByText("正常")).not.toBeInTheDocument();
  });

  it("跑在別的程序的排程照樣列出，但不給「立即執行」", async () => {
    // ⚠️ 2026-07-27 修掉的盲區：RAG 週更住在 rag_worker，原本這一頁完全看不到它。
    // 現在看得到了，但按不動——它動輒數小時，不該由一條後台請求拖著跑。
    vi.mocked(getMeta).mockResolvedValue({ internal_testing: true });
    vi.mocked(listJobs).mockResolvedValue({
      jobs: [
        job(),
        job({
          job_name: "rag-weekly-refresh",
          cron: "0 3 * * 0",
          owner: "rag_worker",
          can_run_now: false,
          last_run_at: null,
          due_at: null,
          never_ran: true,
        }),
      ],
      meta: {
        overdue: [],
        never_ran: ["rag-weekly-refresh"],
        warnings: ["有 1 支排程從未執行過：rag-weekly-refresh（rag_worker）"],
      },
    } as never);

    render(<SystemPage />);

    expect(await screen.findByText("rag-weekly-refresh")).toBeInTheDocument();
    // 該去重啟誰要看得見。
    expect(screen.getByText("rag_worker")).toBeInTheDocument();
    expect(screen.getByText("由 rag_worker 執行")).toBeInTheDocument();
    // 排程器自己的那支照樣可按，兩者不可一起關掉。
    expect(screen.getAllByRole("button", { name: "立即執行（內測）" })).toHaveLength(1);
  });
});
