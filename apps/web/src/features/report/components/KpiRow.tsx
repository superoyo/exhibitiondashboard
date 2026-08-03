import { Card } from '@/components/ui/card';
import { fmt } from '@/lib/format';
import type { ReportTotals } from '@/features/report/lib/metrics';

function Kpi({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card className="p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 text-xl font-bold sm:text-2xl">{value}</div>
      <div className="mt-1 text-xs text-muted-foreground">{sub ?? ''}</div>
    </Card>
  );
}

export function KpiRow({ totals }: { totals: ReportTotals }) {
  return (
    <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
      <Kpi label="Total Views" value={fmt(totals.totalViews)} sub={`${totals.postCount} โพสต์`} />
      <Kpi label="Total Engagement" value={fmt(totals.totalEngagement)} sub="like+cmt+share+save" />
      <Kpi label="Avg ER" value={`${totals.avgEr.toFixed(2)}%`} sub="engagement/views" />
      <Kpi label="โพสต์" value={String(totals.postCount)} />
      <Kpi label="KOL" value={String(totals.kolCount)} />
      <Kpi label="Followers รวม" value={fmt(totals.reach)} sub="reach" />
    </div>
  );
}

/** Likes / comments / shares / saves, each as a share of total engagement. */
export function EngagementBreakdown({
  totals,
  byKind,
}: {
  totals: ReportTotals;
  byKind: { likes: number; comments: number; shares: number; saves: number };
}) {
  const rows: Array<[emoji: string, label: string, value: number]> = [
    ['❤️', 'Likes', byKind.likes],
    ['💬', 'Comments', byKind.comments],
    ['🔁', 'Shares', byKind.shares],
    ['🔖', 'Saves', byKind.saves],
  ];

  return (
    <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
      {rows.map(([emoji, label, value]) => (
        <Card key={label} className="p-3">
          <div className="text-xs text-muted-foreground">
            {emoji} {label}
          </div>
          <div className="mt-1 text-xl font-bold">{fmt(value)}</div>
          <div className="mt-1 text-xs text-muted-foreground">
            {totals.totalEngagement ? ((value / totals.totalEngagement) * 100).toFixed(1) : 0}% ของ
            engagement
          </div>
        </Card>
      ))}
    </div>
  );
}
