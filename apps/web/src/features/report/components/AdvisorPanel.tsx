import type { AdvisorGrade, AdvisorPost } from '@kol/shared';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { getAdvisor, getViewAdvisor } from '@/features/report/api/reportApi';

/**
 * Performance Analysis, spec v2: one GRADE line per post, anchored to the sold
 * target — the team judged v1's verdicts and talking points "กว้างและเยอะไป".
 * Display only; the trigger lives in the top action bar.
 *
 * Shown on the client link too (2026-09-01): the OUTPUT is grades and
 * engagement figures only — the prompt bans money in it, even though the
 * analysis input weighs selling prices. On a /v/ link the stored result is
 * read through the token endpoint; RUNNING an analysis stays logged-in.
 */

const PAGE_SIZE = 15;

const GRADE: Record<AdvisorGrade, { label: string; chip: string; order: number }> = {
  ABOVE: { label: '🟢 เกินเป้า', chip: 'bg-emerald-100 text-emerald-900', order: 0 },
  ON_TRACK: { label: '🟡 ตามเป้า', chip: 'bg-amber-100 text-amber-900', order: 1 },
  BELOW: { label: '🟠 ต่ำกว่าเป้า', chip: 'bg-orange-100 text-orange-900', order: 2 },
  TOO_EARLY: { label: '⚪ รอประเมิน', chip: 'bg-slate-100 text-slate-600', order: 3 },
};

function PostLine({ post }: { post: AdvisorPost }) {
  const g = GRADE[post.grade] ?? GRADE.ON_TRACK;
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 border-b border-border py-1.5 last:border-0">
      <span className={cn('rounded px-1.5 py-0.5 text-[11px] font-bold', g.chip)}>{g.label}</span>
      {post.boost ? (
        <span className="rounded bg-fuchsia-100 px-1.5 py-0.5 text-[11px] font-bold text-fuchsia-900">
          🚀 น่าบูส
        </span>
      ) : null}
      <span className="font-semibold">{post.handle}</span>
      <span className="text-xs text-muted-foreground">{post.platform}</span>
      <span className="w-full text-xs text-muted-foreground sm:w-auto sm:flex-1">
        {post.reason}
      </span>
    </div>
  );
}

export function AdvisorPanel({
  campaign,
  running,
  statusMessage,
  viewOnly = false,
  viewToken = '',
}: {
  campaign: string;
  /** True while a run started from the top button is in progress. */
  running: boolean;
  statusMessage?: string;
  /** Client-facing: no "press the button" hints — the reader has no button. */
  viewOnly?: boolean;
  /** Set on /v/ links (no session): read the stored result by token instead. */
  viewToken?: string;
}) {
  const advisor = useQuery({
    queryKey: ['report', 'advisor', campaign, viewToken],
    queryFn: () => (viewToken ? getViewAdvisor(viewToken) : getAdvisor(campaign)),
    enabled: Boolean(campaign),
  });

  // Pull the fresh result in the moment a run finishes (running: true → false).
  const refetch = advisor.refetch;
  useEffect(() => {
    if (!running) void refetch();
  }, [running, refetch]);

  const data = advisor.data;
  const result = data?.is_set ? data.result : undefined;
  // Results stored by the v1 spec have no `posts` — ask for a fresh run rather
  // than half-rendering a shape this panel no longer speaks.
  const posts = [...(result?.posts ?? [])].sort(
    (a, b) => (GRADE[a.grade]?.order ?? 9) - (GRADE[b.grade]?.order ?? 9),
  );
  const staleFormat = Boolean(result) && !result?.posts;
  const generated = data?.generated_at
    ? new Date(data.generated_at).toLocaleString('th-TH', {
        dateStyle: 'medium',
        timeStyle: 'short',
      })
    : '';
  const ageDays = data?.generated_at
    ? Math.floor((Date.now() - new Date(data.generated_at).getTime()) / 86_400_000)
    : 0;
  const counts = posts.reduce<Record<string, number>>((acc, p) => {
    acc[p.grade] = (acc[p.grade] ?? 0) + 1;
    return acc;
  }, {});
  const boostCount = posts.filter((p) => p.boost).length;

  // Big campaigns produce 40+ graded lines — filter by grade and page by 15,
  // the same reading pattern as the comment panel (team ask, 2026-09-02).
  // Everything is already client-side, so both are plain state.
  const [gradeFilter, setGradeFilter] = useState<'' | 'BOOST' | AdvisorGrade>('');
  const [offset, setOffset] = useState(0);
  // A new campaign or a fresh run starts back at "everything, page 1".
  useEffect(() => {
    setGradeFilter('');
    setOffset(0);
  }, [campaign, data?.generated_at]);

  const filtered =
    gradeFilter === ''
      ? posts
      : gradeFilter === 'BOOST'
        ? posts.filter((p) => p.boost)
        : posts.filter((p) => p.grade === gradeFilter);
  const pageRows = filtered.slice(offset, offset + PAGE_SIZE);
  const from = filtered.length === 0 ? 0 : offset + 1;
  const to = Math.min(offset + PAGE_SIZE, filtered.length);

  function pick(key: '' | 'BOOST' | AdvisorGrade) {
    setGradeFilter(key);
    setOffset(0);
  }

  const chips: { key: '' | 'BOOST' | AdvisorGrade; label: string; count: number }[] = [
    { key: '', label: 'ทั้งหมด', count: posts.length },
    ...(['ABOVE', 'ON_TRACK', 'BELOW', 'TOO_EARLY'] as const).map((gr) => ({
      key: gr,
      label: GRADE[gr].label,
      count: counts[gr] ?? 0,
    })),
    { key: 'BOOST' as const, label: '🚀 น่าบูส', count: boostCount },
  ];

  // A client can't run an analysis, so a card full of "press the button"
  // would only advertise a control they don't have — show the panel to them
  // only once a result in the current format exists.
  if (viewOnly && (!result || staleFormat)) return null;

  return (
    <Card>
      <CardContent className="p-4">
        <h3 className="mb-1 font-semibold">📈 Performance Analysis</h3>

        {running ? (
          <p className="mb-2 text-sm text-muted-foreground">
            ⏳ {statusMessage || 'กำลังวิเคราะห์…'} (ปิดหน้านี้ได้ งานเดินต่อเอง)
          </p>
        ) : null}

        {!result && !running ? (
          <p className="text-sm text-muted-foreground">
            ยังไม่เคยวิเคราะห์แคมเปญนี้ — กดปุ่ม <strong>📈 Performance Analysis</strong> ด้านบน
            (หลัง Refresh Data แล้ว) ระบบจะให้เกรดทุกโพสต์เทียบ KPI ที่ขาย ค่ากลางแคมเปญ
            และผลงานเก่าของช่อง
          </p>
        ) : null}

        {staleFormat && !running ? (
          <p className="text-sm text-amber-700">
            รูปแบบการวิเคราะห์เปลี่ยนเป็นแบบเกรดแล้ว — กด <strong>📈 Performance Analysis</strong>{' '}
            อีกครั้งเพื่อได้ผลรูปแบบใหม่
          </p>
        ) : null}

        {result && !staleFormat ? (
          <>
            <p className="mb-1 text-xs text-muted-foreground">
              วิเคราะห์เมื่อ {generated}
              {ageDays >= 7 ? (
                <span className="font-semibold text-amber-700">
                  {' '}
                  · ผ่านมา {ageDays} วัน{viewOnly ? '' : ' — กดวิเคราะห์ใหม่ก่อนใช้'}
                </span>
              ) : null}
              {' · '}ลงงานแล้ว {result.posted_count} · รอลงงาน {result.pending_count}
            </p>
            <p className="mb-2 rounded-lg border border-brand-400 bg-brand-200/40 p-2 text-sm">
              {result.campaign_summary}
            </p>

            {/* Grade chips — the per-grade counts live here now instead of the
                meta line. A 0-count chip stays clickable, like the comment
                panel: an empty group is itself an answer. */}
            <div className="mb-2 flex flex-wrap gap-1.5">
              {chips.map((c) => (
                <button
                  key={c.key || 'all'}
                  type="button"
                  onClick={() => pick(c.key)}
                  className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${
                    gradeFilter === c.key
                      ? 'border-transparent bg-slate-800 text-white'
                      : 'hover:bg-muted'
                  }`}
                >
                  {c.label} <span className="tabular-nums opacity-70">{c.count}</span>
                </button>
              ))}
            </div>

            {filtered.length === 0 ? (
              <div className="py-4 text-center text-sm text-muted-foreground">
                ไม่มีโพสต์ในกลุ่มนี้
              </div>
            ) : (
              <div>
                {pageRows.map((p) => (
                  <PostLine key={p.handle + p.platform + p.reason.slice(0, 12)} post={p} />
                ))}
              </div>
            )}

            {filtered.length > PAGE_SIZE ? (
              <div className="mt-3 flex items-center justify-between gap-3">
                <span className="text-xs text-muted-foreground">
                  {from}–{to} จาก {filtered.length}
                </span>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={offset === 0}
                    onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                  >
                    ← ก่อนหน้า
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={to >= filtered.length}
                    onClick={() => setOffset(offset + PAGE_SIZE)}
                  >
                    ถัดไป →
                  </Button>
                </div>
              </div>
            ) : null}
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
