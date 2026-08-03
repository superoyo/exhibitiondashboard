import { useMemo, useState } from 'react';
import type { ReportRecordDerived } from '@kol/shared';

import { CachedImage } from '@/components/common/CachedImage';
import { PlatformBadge } from '@/components/common/PlatformBadge';
import { fmt, fmtFull } from '@/lib/format';
import type { CategoryColors } from '@/lib/colors';
import { cn } from '@/lib/utils';
import { erText } from '@/features/report/lib/metrics';

type SortKey = keyof Pick<
  ReportRecordDerived,
  | 'category'
  | 'username'
  | 'followers'
  | 'views'
  | 'likes'
  | 'comments'
  | 'shares'
  | 'saves'
  | 'er'
  | 'posted'
>;

const COLUMNS: Array<{ key: SortKey; label: string; align?: 'right' }> = [
  { key: 'category', label: 'หมวด' },
  { key: 'username', label: 'KOL' },
  { key: 'followers', label: 'Followers', align: 'right' },
  { key: 'views', label: 'Views', align: 'right' },
  { key: 'likes', label: '❤️ Likes', align: 'right' },
  { key: 'comments', label: '💬 Cmt', align: 'right' },
  { key: 'shares', label: '🔁 Share', align: 'right' },
  { key: 'saves', label: '🔖 Save', align: 'right' },
  { key: 'er', label: 'ER%', align: 'right' },
  { key: 'posted', label: 'โพสต์เมื่อ' },
];

export function PostsTable({
  rows,
  colors,
}: {
  rows: ReportRecordDerived[];
  colors: CategoryColors;
}) {
  const [sortKey, setSortKey] = useState<SortKey>('views');
  const [ascending, setAscending] = useState(false);

  const sorted = useMemo(() => {
    return [...rows].sort((a, b) => {
      const x = a[sortKey];
      const y = b[sortKey];
      if (typeof x === 'string' || typeof y === 'string') {
        // localeCompare so Thai category/KOL names order correctly.
        return ascending ? String(x).localeCompare(String(y)) : String(y).localeCompare(String(x));
      }
      return ascending ? Number(x) - Number(y) : Number(y) - Number(x);
    });
  }, [rows, sortKey, ascending]);

  function toggleSort(key: SortKey) {
    if (key === sortKey) setAscending((a) => !a);
    else {
      setSortKey(key);
      setAscending(false);
    }
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-muted-foreground">
            {COLUMNS.map((col) => (
              <th
                key={col.key}
                onClick={() => toggleSort(col.key)}
                aria-sort={sortKey === col.key ? (ascending ? 'ascending' : 'descending') : 'none'}
                className={cn(
                  'cursor-pointer select-none whitespace-nowrap py-2 pr-3 font-normal',
                  col.align === 'right' && 'text-right',
                )}
              >
                {col.label}
                {sortKey === col.key && (ascending ? ' ▲' : ' ▼')}
              </th>
            ))}
            <th className="py-2 font-normal">ลิงก์</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr
              key={`${row.username}-${row.platform}-${row.url}`}
              className="border-b border-border hover:bg-black/5"
            >
              <td className="py-2 pr-3">
                <span className="chip" style={{ background: colors.colorOf(row.category) }}>
                  {row.category}
                </span>
              </td>
              <td className="pr-3 font-medium">
                <span className="inline-flex items-center gap-2">
                  <CachedImage
                    src={row.avatar}
                    className="size-10 flex-none rounded-full bg-slate-200 object-cover"
                  />
                  @{row.username}{' '}
                  <PlatformBadge platform={row.platform} label={row.platform_label} />
                </span>
              </td>
              <td className="pr-3 text-right">{fmt(row.followers)}</td>
              <td className="pr-3 text-right font-semibold">{fmtFull(row.views)}</td>
              <td className="pr-3 text-right">{fmtFull(row.likes)}</td>
              <td className="pr-3 text-right">{fmtFull(row.comments)}</td>
              <td className="pr-3 text-right">{fmtFull(row.shares)}</td>
              <td className="pr-3 text-right">{fmtFull(row.saves)}</td>
              <td className="pr-3 text-right">{erText(row)}</td>
              <td className="pr-3 text-muted-foreground">{row.posted || ''}</td>
              <td>
                {row.url && (
                  <a href={row.url} target="_blank" rel="noopener noreferrer">
                    เปิด ↗
                  </a>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
