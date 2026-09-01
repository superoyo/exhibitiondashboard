import type { AdvisorGrade, AdvisorPost } from '@kol/shared';
import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';

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
              {(['ABOVE', 'ON_TRACK', 'BELOW', 'TOO_EARLY'] as const)
                .filter((gr) => counts[gr])
                .map((gr) => ` · ${GRADE[gr].label} ${counts[gr]}`)
                .join('')}
            </p>
            <p className="mb-2 rounded-lg border border-brand-400 bg-brand-200/40 p-2 text-sm">
              {result.campaign_summary}
            </p>
            <div>
              {posts.map((p) => (
                <PostLine key={p.handle + p.platform + p.reason.slice(0, 12)} post={p} />
              ))}
            </div>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
