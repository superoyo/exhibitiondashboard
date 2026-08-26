import type { AdvisorKol, AdvisorVerdict } from '@kol/shared';
import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';

import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { getAdvisor } from '@/features/report/api/reportApi';

/**
 * Performance Analysis — the team's analyst prompt run over the campaign's
 * numbers, one verdict per posted KOL. Display only: the trigger lives in the
 * top action bar with the other buttons (ReportActions), at the team's request.
 *
 * INTERNAL ONLY. Mounted behind !viewOnly and its endpoints require login: the
 * analysis input carries selling prices, and internal_note may quote CPV/CPE
 * derived from them. Never render any of this on a client link.
 *
 * The stored result is shown with its timestamp: boost advice has a ~7-day
 * shelf life, so WHEN it was generated is part of the answer.
 */

const VERDICT: Record<AdvisorVerdict, { label: string; chip: string; order: number }> = {
  BOOST_NOW: { label: '🚀 ควรบูสตอนนี้', chip: 'bg-emerald-100 text-emerald-900', order: 0 },
  REBOOK: { label: '🔁 น่าจ้างซ้ำ', chip: 'bg-sky-100 text-sky-900', order: 1 },
  SOLID: { label: '✅ ตามมาตรฐาน', chip: 'bg-slate-100 text-slate-700', order: 2 },
  WATCH: { label: '👀 เฝ้าดู', chip: 'bg-amber-100 text-amber-900', order: 3 },
  PENDING: { label: '⏳ ยังไม่ลงงาน', chip: 'bg-slate-50 text-muted-foreground', order: 4 },
};

function KolCard({ kol }: { kol: AdvisorKol }) {
  const v = VERDICT[kol.verdict] ?? VERDICT.SOLID;
  return (
    <div className="rounded-lg border p-3">
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <span className={cn('rounded px-2 py-0.5 text-xs font-bold', v.chip)}>{v.label}</span>
        <span className="font-semibold">{kol.handle}</span>
        <span className="text-xs text-muted-foreground">
          {kol.platform} · {kol.tier} · {kol.category}
        </span>
      </div>
      <p className="text-xs text-muted-foreground">{kol.evidence}</p>
      <p className="mt-1.5 text-sm">
        <span className="font-semibold">พูดกับลูกค้า:</span> {kol.ae_talking_point}
      </p>
      {kol.internal_note ? (
        <p className="mt-1 rounded bg-muted px-2 py-1 text-xs text-muted-foreground">
          🔒 ภายใน: {kol.internal_note}
        </p>
      ) : null}
      <p className="mt-1 text-[10px] text-muted-foreground">ความมั่นใจ: {kol.confidence}</p>
    </div>
  );
}

export function AdvisorPanel({
  campaign,
  running,
  statusMessage,
}: {
  campaign: string;
  /** True while a run started from the top button is in progress. */
  running: boolean;
  statusMessage?: string;
}) {
  const advisor = useQuery({
    queryKey: ['report', 'advisor', campaign],
    queryFn: () => getAdvisor(campaign),
    enabled: Boolean(campaign),
  });

  // Pull the fresh result in the moment a run finishes (running: true → false).
  const refetch = advisor.refetch;
  useEffect(() => {
    if (!running) void refetch();
  }, [running, refetch]);

  const data = advisor.data;
  const result = data?.is_set ? data.result : undefined;
  const kols = [...(result?.kols ?? [])].sort(
    (a, b) => (VERDICT[a.verdict]?.order ?? 9) - (VERDICT[b.verdict]?.order ?? 9),
  );
  const generated = data?.generated_at
    ? new Date(data.generated_at).toLocaleString('th-TH', {
        dateStyle: 'medium',
        timeStyle: 'short',
      })
    : '';
  // Boost advice expires — say so once it is old instead of letting a stale
  // recommendation read as current.
  const ageDays = data?.generated_at
    ? Math.floor((Date.now() - new Date(data.generated_at).getTime()) / 86_400_000)
    : 0;

  if (!result && !running) {
    return (
      <Card>
        <CardContent className="p-4">
          <h3 className="mb-1 font-semibold">📈 Performance Analysis (เฉพาะทีม)</h3>
          <p className="text-sm text-muted-foreground">
            ยังไม่เคยวิเคราะห์แคมเปญนี้ — กดปุ่ม <strong>📈 Performance Analysis</strong> ด้านบน
            (หลัง Refresh Data แล้ว) AI จะชี้ว่าโพสต์ไหนควรบูส คนไหนน่าจ้างซ้ำ
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="p-4">
        <h3 className="mb-1 font-semibold">📈 Performance Analysis (เฉพาะทีม)</h3>

        {running ? (
          <p className="mb-2 text-sm text-muted-foreground">
            ⏳ {statusMessage || 'กำลังวิเคราะห์…'} (ปิดหน้านี้ได้ งานเดินต่อเอง)
          </p>
        ) : null}

        {result ? (
          <>
            <p className="mb-1 text-xs text-muted-foreground">
              วิเคราะห์เมื่อ {generated}
              {ageDays >= 7 ? (
                <span className="font-semibold text-amber-700">
                  {' '}
                  · ผ่านมา {ageDays} วัน — คำแนะนำบูสอาจหมดอายุ กดวิเคราะห์ใหม่ก่อนใช้
                </span>
              ) : null}
              {' · '}ลงงานแล้ว {result.posted_count} · รอลงงาน {result.pending_count}
            </p>
            <p className="mb-3 rounded-lg border border-brand-400 bg-brand-200/40 p-2 text-sm">
              {result.campaign_summary}
            </p>
            <div className="grid gap-2 lg:grid-cols-2">
              {kols.map((k) => (
                <KolCard key={k.handle + k.platform} kol={k} />
              ))}
            </div>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
