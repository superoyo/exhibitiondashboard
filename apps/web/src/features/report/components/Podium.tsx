import { useMemo } from 'react';
import { FILTER_ALL, type ReportMetric, type ReportRecordDerived } from '@kol/shared';

import { Card } from '@/components/ui/card';
import { CachedImage } from '@/components/common/CachedImage';
import { PlatformBadge } from '@/components/common/PlatformBadge';
import { SegmentedControl } from '@/components/common/SegmentedControl';
import { fmt } from '@/lib/format';
import { platformMeta } from '@/lib/platforms';
import type { CategoryColors } from '@/lib/colors';
import { erText } from '@/features/report/lib/metrics';

const MEDALS = ['🥇', '🥈', '🥉'];

/** Label + value formatter per podium metric. */
const METRIC_META: Record<ReportMetric, { label: string; format: (v: number) => string }> = {
  views: { label: 'Views', format: fmt },
  engagement: { label: 'Engagement', format: fmt },
  er: { label: 'ER%', format: (v) => `${v.toFixed(2)}%` },
  likes: { label: 'Likes', format: fmt },
  saves: { label: 'Saves', format: fmt },
};

interface PodiumProps {
  rows: ReportRecordDerived[];
  categories: string[];
  platforms: string[];
  colors: CategoryColors;
  category: string;
  platform: string;
  metric: ReportMetric;
  onCategoryChange: (value: string) => void;
  onPlatformChange: (value: string) => void;
  onMetricChange: (value: ReportMetric) => void;
}

function PodiumCard({
  row,
  rank,
  metric,
  color,
}: {
  row: ReportRecordDerived;
  rank: number;
  metric: ReportMetric;
  color: string;
}) {
  const meta = METRIC_META[metric];

  return (
    <Card
      className="overflow-hidden"
      style={rank === 0 ? { border: `2px solid ${color}` } : undefined}
    >
      <a
        href={row.url || undefined}
        target="_blank"
        rel="noopener noreferrer"
        className="relative block h-[190px] overflow-hidden bg-slate-200"
      >
        <div className="absolute inset-0 flex items-center justify-center text-[0.8rem] text-slate-400">
          ตัวอย่างคอนเทนต์
        </div>
        <CachedImage src={row.thumb} className="relative block h-[190px] w-full object-cover" />
        <div
          className="absolute left-2 top-2 text-3xl"
          style={{ filter: 'drop-shadow(0 1px 2px rgba(0,0,0,.6))' }}
        >
          {MEDALS[rank]}
        </div>
        <span className="chip absolute right-2 top-3" style={{ background: color }}>
          {row.category}
        </span>
        <div
          className="absolute inset-x-0 bottom-0 px-3 py-2 text-sm font-semibold text-white"
          style={{ background: 'linear-gradient(transparent,rgba(0,0,0,.7))' }}
        >
          ▶ ดูคลิปจริง
        </div>
      </a>

      <div className="p-3">
        <div className="flex items-center gap-2">
          <CachedImage
            src={row.avatar}
            className="size-[42px] flex-none rounded-full bg-slate-200 object-cover"
            style={{ border: `2px solid ${color}` }}
          />
          <div className="min-w-0">
            <div className="truncate text-lg font-bold leading-tight">@{row.username}</div>
            <div className="truncate text-xs text-muted-foreground">{row.nickname || ''}</div>
            <div className="mt-1">
              <PlatformBadge platform={row.platform} label={row.platform_label} />
            </div>
          </div>
        </div>

        <div className="mt-2 text-2xl font-extrabold" style={{ color }}>
          {meta.format(row[metric])}
        </div>
        <div className="text-xs text-muted-foreground">{meta.label}</div>

        <div className="mt-3 grid grid-cols-3 gap-y-1 text-xs text-slate-700">
          <div>👁 {fmt(row.views)}</div>
          <div>❤️ {fmt(row.likes)}</div>
          <div>💬 {fmt(row.comments)}</div>
          <div>🔁 {fmt(row.shares)}</div>
          <div>🔖 {fmt(row.saves || 0)}</div>
          <div>📊 {erText(row)}</div>
        </div>

        {row.url ? (
          <a href={row.url} target="_blank" rel="noopener noreferrer" className="post-link">
            🔗 ดูโพสต์ต้นทาง ↗
          </a>
        ) : (
          <span className="post-link disabled">— ยังไม่มีลิงก์โพสต์ —</span>
        )}
      </div>
    </Card>
  );
}

export function Podium({
  rows,
  categories,
  platforms,
  colors,
  category,
  platform,
  metric,
  onCategoryChange,
  onPlatformChange,
  onMetricChange,
}: PodiumProps) {
  const pool = useMemo(() => {
    let result = rows;
    if (category !== FILTER_ALL) result = result.filter((r) => r.category === category);
    if (platform !== FILTER_ALL) result = result.filter((r) => r.platform === platform);
    return result;
  }, [rows, category, platform]);

  const top = useMemo(
    () => [...pool].sort((a, b) => b[metric] - a[metric]).slice(0, 3),
    [pool, metric],
  );

  /** Human description of the active filter, for the empty/thin states. */
  const filterLabel =
    [
      category !== FILTER_ALL ? category : null,
      platform !== FILTER_ALL ? platformMeta(platform).label : null,
    ]
      .filter(Boolean)
      .join(' + ') || FILTER_ALL;

  return (
    <section className="mb-5 rounded-[14px] border border-border bg-card p-4 shadow-card">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-lg font-semibold">🏆 Top 3 KOL</h3>
        <SegmentedControl
          options={Object.entries(METRIC_META).map(([value, m]) => ({
            value,
            label: m.label,
          }))}
          value={metric}
          onChange={(v) => onMetricChange(v as ReportMetric)}
          ariaLabel="เลือกตัวชี้วัด"
        />
      </div>

      <SegmentedControl
        className="mb-2"
        label="หมวด:"
        options={[FILTER_ALL, ...categories].map((c) => ({ value: c, label: c }))}
        value={category}
        onChange={onCategoryChange}
      />
      <SegmentedControl
        className="mb-4"
        label="แพลตฟอร์ม:"
        options={[
          { value: FILTER_ALL, label: FILTER_ALL },
          ...platforms.map((p) => ({ value: p, label: platformMeta(p).label })),
        ]}
        value={platform}
        onChange={onPlatformChange}
      />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {top.length === 0 ? (
          <div className="col-span-full text-sm text-muted-foreground">
            ไม่มีโพสต์ในตัวกรอง &quot;<b>{filterLabel}</b>&quot;
          </div>
        ) : (
          <>
            {top.map((row, i) => (
              <PodiumCard
                key={`${row.username}-${row.platform}`}
                row={row}
                rank={i}
                metric={metric}
                color={colors.colorOf(row.category)}
              />
            ))}
            {/* Say so when the filter has fewer than 3 posts, rather than
                silently showing a short podium. */}
            {pool.length < 3 && (
              <Card className="flex flex-col items-center justify-center border-dashed p-4 text-center text-muted-foreground">
                <div className="mb-1 text-2xl">ℹ️</div>
                <div className="text-sm">
                  ตัวกรอง &quot;<b>{filterLabel}</b>&quot; มีแค่ <b>{pool.length}</b> โพสต์
                </div>
              </Card>
            )}
          </>
        )}
      </div>
    </section>
  );
}
