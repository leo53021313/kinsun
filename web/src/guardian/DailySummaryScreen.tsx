/**
 * 每日摘要（W6）：日期切換、一段摘要文字、分享給家人。
 *
 * ⚠️ **後端只回一段純文字。** `DailySummary` 的真實欄位是 `{date, content, created_at}`
 * （`shared/types.ts`）。設計稿那個三層結構（原話照登／阿白注意到的／四個事實數字）
 * 沒有對應欄位——App 那批核對型別後也是照真實欄位做的，web 一樣。要做三層版本得
 * 後端先把摘要拆成結構化輸出，那是另一項待辦，不是這裡少做。
 *
 * ⚠️ 清單由 API 依日期**由新到舊**排序：index 0 是最新一天，往「前一天」看是 index+1。
 * 這個方向很容易寫反，兩顆箭頭的停用條件也跟著反，所以兩者都寫成測試。
 */

import { useCallback, useEffect, useState } from "react";

import type { DailySummary } from "kinsun-shared/types";

import { GuardianSession } from "@/session/contexts";
import { makeSignOutOnAuthError } from "@/session/useSignOutOnAuthError";
import { strings } from "@/strings";
import { Button } from "@/ui/Button";
import { EmptyHint, ErrorText, NoticeText } from "@/ui/Feedback";
import { Section } from "@/ui/Section";

import { listDailySummaries } from "./api";
import { buildShareText } from "./guardianFormat";

export function DailySummaryScreen(props: { elderId: string }) {
  const { elderId } = props;
  const { session, signOut } = GuardianSession.useSession();
  const [items, setItems] = useState<DailySummary[]>([]);
  const [index, setIndex] = useState(0);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [attempt, setAttempt] = useState(0);

  const token = session?.token ?? "";

  useEffect(() => {
    if (!token) return;
    const signOutOn401 = makeSignOutOnAuthError(signOut);
    let alive = true;
    void (async () => {
      try {
        const list = await listDailySummaries(elderId, token);
        if (alive) {
          setItems(list);
          setIndex(0);
        }
      } catch (exc) {
        if (signOutOn401(exc)) return;
        if (alive) setError(strings.common.loadFailed);
      } finally {
        if (alive) setLoaded(true);
      }
    })();
    return () => {
      alive = false;
    };
  }, [elderId, token, attempt, signOut]);

  const current = items[index];

  const share = useCallback(async () => {
    if (!current) return;
    const text = buildShareText(current);
    setError("");
    setNotice("");
    // ⚠️ 桌機瀏覽器多半沒有 `navigator.share`（那是行動裝置的系統分享面板）。
    // 退回複製到剪貼簿——家屬拿得到內容就達成目的了，跳一個「不支援」的錯誤只是
    // 把責任推回去給他。
    if (typeof navigator.share === "function") {
      try {
        await navigator.share({ text });
        return;
      } catch (exc) {
        // 使用者自己按取消不是錯誤，不要因此跳紅字。
        if (exc instanceof DOMException && exc.name === "AbortError") return;
      }
    }
    try {
      await navigator.clipboard.writeText(text);
      setNotice(strings.dailySummary.copied);
    } catch {
      setError(strings.dailySummary.shareFailed);
    }
  }, [current]);

  if (!loaded) {
    return (
      <div className="flex flex-col gap-3 p-4">
        <EmptyHint text={strings.common.loading} />
      </div>
    );
  }

  if (error && items.length === 0) {
    return (
      <div className="flex flex-col gap-3 p-4">
        <ErrorText message={error} />
        <Button
          label={strings.common.retry}
          variant="outline"
          onClick={() => {
            setError("");
            setLoaded(false);
            setAttempt((value) => value + 1);
          }}
        />
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="flex flex-col gap-3 p-4">
        <EmptyHint text={strings.elderDetail.noSummaries} />
      </div>
    );
  }

  const isOldest = index >= items.length - 1;
  const isNewest = index === 0;

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="flex items-center justify-between rounded-pill border border-line bg-surface p-1">
        <ArrowButton
          label={strings.dailySummary.prevDay}
          disabled={isOldest}
          onClick={() => setIndex((value) => Math.min(value + 1, items.length - 1))}
          glyph="‹"
        />
        <span className="text-base font-bold text-ink">{current.date}</span>
        <ArrowButton
          label={strings.dailySummary.nextDay}
          disabled={isNewest}
          onClick={() => setIndex((value) => Math.max(value - 1, 0))}
          glyph="›"
        />
      </div>

      <ErrorText message={error} />
      <NoticeText message={notice} />

      <Section title={strings.dailySummary.section}>
        <p className="text-lg leading-relaxed text-ink">{current.content}</p>
      </Section>

      <p className="text-base leading-relaxed text-ink-soft">
        {strings.dailySummary.disclaimer}
      </p>

      <Button label={strings.dailySummary.share} onClick={() => void share()} />
    </div>
  );
}

function ArrowButton(props: {
  label: string;
  glyph: string;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={props.label}
      disabled={props.disabled}
      onClick={props.onClick}
      className="flex size-12 items-center justify-center rounded-full text-2xl font-bold text-primary disabled:cursor-not-allowed disabled:text-ink-soft disabled:opacity-45 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
    >
      <span aria-hidden>{props.glyph}</span>
    </button>
  );
}
