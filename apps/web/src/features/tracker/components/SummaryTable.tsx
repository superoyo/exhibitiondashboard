import { useMemo, useState } from 'react';
import { TRACKER_GROUP_COLORS, type TrackerKol } from '@kol/shared';

import { deltaClass, fmtCompact, fmtDeltaPct } from '@/lib/format';
import { cn } from '@/lib/utils';

type SortKey = keyof Pick<
  TrackerKol,
  | 'display'
  | 'group'
  | 'followers'
  | 'posts_7d'
  | 'views_7d'
  | 'delta_views_pct'
  | 'engagement_rate'
>;

const COLUMNS: Array<{ key: SortKey; label: string; align?: 'right' }> = [
  { key: 'display', label: 'KOL' },
  { key: 'group', label: 'กลุ่ม' },
  { key: 'followers', label: 'Followers', align: 'right' },
  { key: 'posts_7d', label: 'โพสต์', align: 'right' },
  { key: 'views_7d', label: 'Views', align: 'right' },
  { key: 'delta_views_pct', label: 'Δ Views', align: 'right' },
  { key: 'engagement_rate', label: 'ER', align: 'right' },
];

const GROUP_FALLBACK = '#475569';

export function SummaryTable({
  kols,
  onSelect,
}: {
  kols: TrackerKol[];
  onSelect: (username: string) => void;
}) {
  const [sortKey, setSortKey] = useState<SortKey>('views_7d');
  const [sortDir, setSortDir] = useState<1 | -1>(-1);

  const sorted = useMemo(() => {
    return [...kols].sort((a, b) => {
      const x = a[sortKey];
      const y = b[sortKey];
      if (typeof x === 'string' || typeof y === 'string') {
        return ((x ?? '') > (y ?? '') ? 1 : -1) * sortDir;
      }
      // null sorts as -1 so "no data" lands at the bottom of a descending sort,
      // rather than at the top as it would if treated as 0.
      return ((x ?? -1) - (y ?? -1)) * sortDir;
    });
  }, [kols, sortKey, sortDir]);

  function toggleSort(key: SortKey) {
    if (key === sortKey) setSortDir((d) => (d === 1 ? -1 : 1));
    else {
      setSortKey(key);
      setSortDir(-1);
    }
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs sm:text-sm">
        <thead className="text-muted-foreground">
          <tr className="border-b border-border text-left">
            {COLUMNS.map((col) => (
              <th
                key={col.key}
                onClick={() => toggleSort(col.key)}
                aria-sort={
                  sortKey === col.key ? (sortDir === 1 ? 'ascending' : 'descending') : 'none'
                }
                className={cn(
                  'cursor-pointer select-none px-2 py-2 font-normal',
                  col.align === 'right' && 'text-right',
                )}
              >
                {col.label}
                {sortKey === col.key && (sortDir === 1 ? ' ▲' : ' ▼')}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((k) => {
            const color = TRACKER_GROUP_COLORS[k.group] ?? GROUP_FALLBACK;
            return (
              <tr key={k.username} className="border-b border-border hover:bg-black/5">
                <td className="py-2 pr-2">
                  <button
                    type="button"
                    onClick={() => onSelect(k.username)}
                    className="text-left font-medium text-blue-600 hover:underline"
                  >
                    {k.display}
                  </button>
                  <div className="text-xs text-muted-foreground">@{k.username}</div>
                </td>
                <td className="px-2 py-2">
                  <span
                    className="whitespace-nowrap rounded-full px-2.5 py-1 text-[0.7rem]"
                    style={{ background: `${color}22`, color }}
                  >
                    {k.group}
                  </span>
                </td>
                <td className="px-2 py-2 text-right">{fmtCompact(k.followers)}</td>
                <td className="px-2 py-2 text-right">{k.posts_7d}</td>
                <td className="px-2 py-2 text-right font-semibold">{fmtCompact(k.views_7d)}</td>
                <td className={cn('px-2 py-2 text-right', deltaClass(k.delta_views_pct))}>
                  {k.delta_views_pct == null ? '–' : fmtDeltaPct(k.delta_views_pct)}
                </td>
                <td className="px-2 py-2 text-right">
                  {k.engagement_rate == null ? '–' : `${(k.engagement_rate * 100).toFixed(2)}%`}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
