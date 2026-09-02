import type { AdvisorPost } from '@kol/shared';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { getAdvisor, getViewAdvisor } from '@/features/report/api/reportApi';

/**
 * Performance Analysis, spec v3 (2026-09-02): one SCORE out of 10 per post,
 * judged on the post's numbers against the sold KPI — the team replaced the
 * 4-grade labels with this. `score: null` = under 3 days old, not judged yet.
 * Display only; the trigger lives in the top action bar.
 *
 * Shown on the client link too: the output is scores, engagement figures and
 * CPM only — raw price/boost sums are banned from it. On a /v/ link the
 * stored result is read through the token endpoint; RUNNING stays logged-in.
 */

const PAGE_SIZE = 15;

type BandKey = 'HIGH' | 'MID' | 'LOW' | 'PENDING';

const BAND: Record<BandKey, { label: string; chip: string }> = {
  HIGH: { label: '🟢 8–10', chip: 'bg-emerald-100 text-emerald-900' },
  MID: { label: '🟡 5–7', chip: 'bg-amber-100 text-amber-900' },
  LOW: { label: '🟠 1–4', chip: 'bg-orange-100 text-orange-900' },
  PENDING: { label: '⚪ รอประเมิน', chip: 'bg-slate-100 text-slate-600' },
};

function bandOf(score: number | null | undefined): BandKey {
  if (typeof score !== 'number') return 'PENDING';
  if (score >= 8) return 'HIGH';
  if (score >= 5) return 'MID';
  return 'LOW';
}

function PostLine({ post }: { post: AdvisorPost }) {
  const band = BAND[bandOf(post.score)];
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 border-b border-border py-1.5 last:border-0">
      <span className={cn('rounded px-1.5 py-0.5 text-[11px] font-bold tabular-nums', band.chip)}>
        {typeof post.score === 'number' ? `${post.score}/10` : '⚪ รอประเมิน'}
      </span>
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
  // v1 results have no `posts`; v2 posts carry `grade` but no `score`. Both
  // get a re-run notice rather than a half-rendered hybrid.
  const rawPosts = result?.posts ?? [];
  const staleFormat =
    Boolean(result) && (!result?.posts || rawPosts.some((p) => p.score === undefined));
  // Sort by score, best first; unjudged posts sink to the bottom.
  const posts = [...rawPosts].sort((a, b) => (b.score ?? -1) - (a.score ?? -1));
  const generated = data?.generated_at
    ? new Date(data.generated_at).toLocaleString('th-TH', {
        dateStyle: 'medium',
        timeStyle: 'short',
      })
    : '';
  const ageDays = data?.generated_at
    ? Math.floor((Date.now() - new Date(data.generated_at).getTime()) / 86_400_000)
    : 0;
  const scored = posts.filter((p) => typeof p.score === 'number');
  const avgScore = scored.length
    ? (scored.reduce((s, p) => s + (p.score ?? 0), 0) / scored.length).toFixed(1)
    : null;
  const counts = posts.reduce<Record<string, number>>((acc, p) => {
    const b = bandOf(p.score);
    acc[b] = (acc[b] ?? 0) + 1;
    return acc;
  }, {});
  const boostCount = posts.filter((p) => p.boost).length;

  // Big campaigns produce 40+ scored lines — filter by band and page by 15,
  // the same reading pattern as the comment panel (team ask, 2026-09-02).
  const [bandFilter, setBandFilter] = useState<'' | 'BOOST' | BandKey>('');
  const [offset, setOffset] = useState(0);
  // A new campaign or a fresh run starts back at "everything, page 1".
  useEffect(() => {
    setBandFilter('');
    setOffset(0);
  }, [campaign, data?.generated_at]);

  const filtered =
    bandFilter === ''
      ? posts
      : bandFilter === 'BOOST'
        ? posts.filter((p) => p.boost)
        : posts.filter((p) => bandOf(p.score) === bandFilter);
  const pageRows = filtered.slice(offset, offset + PAGE_SIZE);
  const from = filtered.length === 0 ? 0 : offset + 1;
  const to = Math.min(offset + PAGE_SIZE, filtered.length);

  function pick(key: '' | 'BOOST' | BandKey) {
    setBandFilter(key);
    setOffset(0);
  }

  const chips: { key: '' | 'BOOST' | BandKey; label: string; count: number }[] = [
    { key: '', label: 'ทั้งหมด', count: posts.length },
    ...(['HIGH', 'MID', 'LOW', 'PENDING'] as const).map((b) => ({
      key: b,
      label: BAND[b].label,
      count: counts[b] ?? 0,
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
            (หลัง Refresh Data แล้ว) ระบบจะให้คะแนนทุกโพสต์เต็ม 10 เทียบ KPI ที่ขาย พร้อมเทียบ CPM
            จากงบบูส
          </p>
        ) : null}

        {staleFormat && !running ? (
          <p className="text-sm text-amber-700">
            รูปแบบการวิเคราะห์เปลี่ยนเป็นคะแนนเต็ม 10 แล้ว — กด{' '}
            <strong>📈 Performance Analysis</strong> อีกครั้งเพื่อได้ผลรูปแบบใหม่
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
              {avgScore ? ` · คะแนนเฉลี่ย ${avgScore}/10` : ''}
            </p>
            <p className="mb-2 rounded-lg border border-brand-400 bg-brand-200/40 p-2 text-sm">
              {result.campaign_summary}
            </p>

            {/* Score-band chips — a 0-count chip stays clickable, like the
                comment panel: an empty group is itself an answer. */}
            <div className="mb-2 flex flex-wrap gap-1.5">
              {chips.map((c) => (
                <button
                  key={c.key || 'all'}
                  type="button"
                  onClick={() => pick(c.key)}
                  className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${
                    bandFilter === c.key
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
