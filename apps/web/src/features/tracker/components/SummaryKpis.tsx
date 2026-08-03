import type { TrackerKpis } from '@kol/shared';

import { Card } from '@/components/ui/card';
import { deltaClass, fmtCompact, fmtDeltaPct } from '@/lib/format';
import { cn } from '@/lib/utils';

/** Label + key + whether the value is a 0..1 ratio rather than a count. */
const KPI_ROWS: Array<[label: string, key: keyof TrackerKpis, isRate?: boolean]> = [
  ['Total Views', 'total_views'],
  ['Total Engagement', 'total_engagement'],
  ['Avg ER', 'avg_engagement_rate', true],
  ['จำนวนโพสต์', 'total_posts'],
  ['KOL Active', 'active_kols'],
  ['Followers รวม', 'total_followers'],
];

export function SummaryKpis({ kpis }: { kpis: TrackerKpis }) {
  return (
    <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-6">
      {KPI_ROWS.map(([label, key, isRate]) => {
        const kpi = kpis[key];
        // The legacy page rendered nothing at all for a missing KPI rather than
        // a zero, so an empty database never reads as "0 views".
        if (!kpi) return null;
        const value = isRate ? `${(kpi.value * 100).toFixed(2)}%` : fmtCompact(kpi.value);
        return (
          <Card key={key} className="p-3">
            <div className="text-xs text-muted-foreground">{label}</div>
            <div className="mt-1 text-lg font-bold sm:text-2xl">{value}</div>
            <div className={cn('mt-0.5 text-xs', deltaClass(kpi.delta_pct))}>
              {kpi.delta_pct == null
                ? '— เทียบเมื่อวาน'
                : `${fmtDeltaPct(kpi.delta_pct)} เทียบเมื่อวาน`}
            </div>
          </Card>
        );
      })}
    </div>
  );
}
