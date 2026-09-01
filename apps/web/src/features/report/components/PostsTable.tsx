import { useMemo, useState } from 'react';
import type { KolKpi, ReportRecordDerived } from '@kol/shared';

import { CachedImage } from '@/components/common/CachedImage';
import { PlatformBadge } from '@/components/common/PlatformBadge';
import { fmt, fmtFull } from '@/lib/format';
import type { CategoryColors } from '@/lib/colors';
import { cn } from '@/lib/utils';
import { erText } from '@/features/report/lib/metrics';
import { tierOf } from '@/features/report/lib/tier';

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

/** `metric: true` = a performance number, hidden from the influencer view. */
const COLUMNS: Array<{ key: SortKey; label: string; align?: 'right'; metric?: true }> = [
  { key: 'category', label: 'หมวด' },
  { key: 'username', label: 'KOL' },
  { key: 'followers', label: 'Followers', align: 'right' },
  { key: 'views', label: 'Views', align: 'right', metric: true },
  { key: 'likes', label: '❤️ Likes', align: 'right', metric: true },
  { key: 'comments', label: '💬 Cmt', align: 'right', metric: true },
  { key: 'shares', label: '🔁 Share', align: 'right', metric: true },
  { key: 'saves', label: '🔖 Save', align: 'right', metric: true },
  { key: 'er', label: 'ER%', align: 'right', metric: true },
  { key: 'posted', label: 'โพสต์เมื่อ' },
];

/** Per-KOL commercial data, keyed by lowercase username. Logged-in views read
 *  it from the roster endpoint; /v/ client links read it token-addressed
 *  (team decision 2026-09-01: the client link shows the commercial picture).
 *  When absent (influencer list, campaign without planner data) the columns
 *  simply do not exist. */
export interface CommercialByUser {
  [username: string]: {
    cost_thb?: number | null;
    boost_thb?: number | null;
    kpis?: KolKpi[];
  };
}

export const KPI_LABEL: Record<string, string> = {
  views: 'Views',
  impressions: 'Imp',
  interaction: 'Interaction',
  reach: 'Reach',
};

/**
 * The number a sold KPI is checked against, from public stats:
 * views→views, interaction→engagement. Impressions and Reach exist only in the
 * creator's own insights — null, and the UI says so instead of inventing one.
 */
export function kpiActual(
  metric: string | null | undefined,
  totals: { views: number; engagement: number } | undefined,
): number | null {
  if (!totals) return null;
  if (metric === 'views') return totals.views;
  if (metric === 'interaction') return totals.engagement;
  return null;
}

/** One KPI rendered as "เป้า unit · %" — shared row/group appearance. */
export function KpiLine({
  kpi,
  totals,
}: {
  kpi: KolKpi;
  totals: { views: number; engagement: number } | undefined;
}) {
  const unit = KPI_LABEL[kpi.metric] ?? kpi.metric ?? '';
  const actual = kpiActual(kpi.metric, totals);
  const pct = actual !== null && kpi.target > 0 ? Math.round((100 * actual) / kpi.target) : null;
  return (
    <span className="whitespace-nowrap">
      {fmt(kpi.target)} {unit}
      {pct !== null ? (
        <span className={cn('ml-1 font-semibold', pct >= 100 ? 'text-state-ok' : 'text-amber-600')}>
          {pct >= 100 ? '✅' : ''} {pct}%
        </span>
      ) : (
        <span className="ml-1 text-[10px] text-muted-foreground">(วัดจากหลังบ้าน)</span>
      )}
    </span>
  );
}

/** "12,500" → "12.5K"-style money, but exact — the team quotes these numbers. */
const baht = (n: number) => `฿${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;

export function PostsTable({
  rows,
  colors,
  hideMetrics = false,
  commercial,
}: {
  rows: ReportRecordDerived[];
  colors: CategoryColors;
  /**
   * Influencer view: drop views/likes/comments/shares/saves/ER. An influencer
   * seeing everyone else's numbers is a different (client) report.
   */
  hideMetrics?: boolean;
  /** Present only on the logged-in team view. */
  commercial?: CommercialByUser;
}) {
  // Sorting by views is meaningless when the column is hidden.
  const [sortKey, setSortKey] = useState<SortKey>(hideMetrics ? 'category' : 'views');
  const [ascending, setAscending] = useState(false);

  const columns = hideMetrics ? COLUMNS.filter((c) => !c.metric) : COLUMNS;
  const showMoney = Boolean(commercial);

  // A KPI target is sold per PERSON, but rows are per platform — so achievement
  // compares the target against the SUM of that person's rows, shown the same
  // on each of their rows. views→views, interaction→engagement; impressions
  // have no public counterpart and show the target with no achieved figure.
  const personTotals = useMemo(() => {
    const t: Record<string, { views: number; engagement: number }> = {};
    if (!commercial) return t;
    for (const r of rows) {
      const k = (t[r.username.toLowerCase()] ??= { views: 0, engagement: 0 });
      k.views += r.views;
      k.engagement += r.engagement;
    }
    return t;
  }, [rows, commercial]);

  function kpiCell(username: string) {
    const kpis = commercial?.[username.toLowerCase()]?.kpis ?? [];
    if (!kpis.length) return <span className="text-muted-foreground">—</span>;
    const totals = personTotals[username.toLowerCase()];
    // One line per sold KPI — a KOL can carry Views AND Engagement at once.
    return (
      <span className="inline-flex flex-col gap-0.5">
        {kpis.map((k) => (
          <KpiLine key={k.metric + k.target} kpi={k} totals={totals} />
        ))}
      </span>
    );
  }

  // One KOL = one visual block (team feedback, Shokubutsu 2026-09-01): a KOL
  // posting on several platforms used to scatter across the table — the TikTok
  // row ranked high while the same person's Facebook/YouTube rows sank to the
  // zero-views bottom, and the money/KPI columns repeated on each row as if
  // billed per platform. Rows are grouped by person; name, หมวด, ค่าตัว, บูส
  // and KPI render once per group, stats stay one line per platform.
  const groups = useMemo(() => {
    const order: string[] = [];
    const by = new Map<string, ReportRecordDerived[]>();
    for (const r of rows) {
      const k = r.username.toLowerCase();
      const list = by.get(k);
      if (list) list.push(r);
      else {
        by.set(k, [r]);
        order.push(k);
      }
    }
    // Within a group: best-performing platform first, zero rows last.
    return order.map((k) => {
      const members = [...(by.get(k) ?? [])].sort(
        (a, b) => b.views - a.views || a.platform_label.localeCompare(b.platform_label),
      );
      return { key: k, rows: members };
    });
  }, [rows]);

  // Sorting orders GROUPS: additive metrics by the person's sum across
  // platforms, followers/ER by their best platform, date by the latest post —
  // so a multi-platform KOL holds one position instead of three.
  const sortedGroups = useMemo(() => {
    const value = (g: { rows: ReportRecordDerived[] }): string | number => {
      const first = g.rows[0];
      if (!first) return '';
      if (sortKey === 'category' || sortKey === 'username') return first[sortKey];
      if (sortKey === 'posted') return g.rows.reduce((m, r) => (r.posted > m ? r.posted : m), '');
      if (sortKey === 'followers' || sortKey === 'er')
        return Math.max(...g.rows.map((r) => Number(r[sortKey]) || 0));
      return g.rows.reduce((s, r) => s + (Number(r[sortKey]) || 0), 0);
    };
    return [...groups].sort((a, b) => {
      const x = value(a);
      const y = value(b);
      if (typeof x === 'string' || typeof y === 'string') {
        // localeCompare so Thai category/KOL names order correctly.
        return ascending ? String(x).localeCompare(String(y)) : String(y).localeCompare(String(x));
      }
      return ascending ? Number(x) - Number(y) : Number(y) - Number(x);
    });
  }, [groups, sortKey, ascending]);

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
            {/* Commercial columns leftmost, per the team's layout. Not sortable
                — they come from the roster, not the record the sorter reads. */}
            {showMoney && (
              <>
                <th className="whitespace-nowrap py-2 pr-3 text-right font-normal">ค่าตัว</th>
                <th className="whitespace-nowrap py-2 pr-3 text-right font-normal">บูส</th>
              </>
            )}
            {columns.map((col) => (
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
            {showMoney && <th className="whitespace-nowrap py-2 pr-3 font-normal">KPI ที่ขาย</th>}
            <th className="py-2 font-normal">ลิงก์</th>
          </tr>
        </thead>
        <tbody>
          {sortedGroups.length === 0 && (
            <tr>
              <td
                colSpan={columns.length + 1 + (showMoney ? 3 : 0)}
                className="py-3 text-muted-foreground"
              >
                — ไม่มี (ทุกคนมี link แล้ว) —
              </td>
            </tr>
          )}
          {sortedGroups.map((g) =>
            g.rows.map((row, i) => {
              const span = g.rows.length;
              const grouped = span > 1;
              const first = i === 0;
              const last = i === span - 1;
              // The one-per-person cells read from the whole group: the top
              // platform's avatar, the first profile link the planner supplied.
              const avatar = g.rows.find((r) => r.avatar)?.avatar ?? '';
              const profileUrl = g.rows.find((r) => r.profile_url)?.profile_url ?? '';
              return (
                <tr
                  key={`${row.username}-${row.platform}-${row.url}`}
                  className={cn(
                    'hover:bg-black/5',
                    // Lighter line between a person's own platforms, full line
                    // between people — the block reads as one KOL.
                    last ? 'border-b border-border' : 'border-b border-border/40',
                  )}
                >
                  {showMoney &&
                    first &&
                    (() => {
                      const c = commercial?.[row.username.toLowerCase()];
                      return (
                        <>
                          <td
                            rowSpan={span}
                            className="whitespace-nowrap py-2 pr-3 text-right tabular-nums"
                          >
                            {c?.cost_thb != null ? baht(c.cost_thb) : ''}
                          </td>
                          <td
                            rowSpan={span}
                            className="whitespace-nowrap py-2 pr-3 text-right tabular-nums"
                          >
                            {c?.boost_thb != null ? baht(c.boost_thb) : ''}
                          </td>
                        </>
                      );
                    })()}
                  {first && (
                    <td rowSpan={span} className="py-2 pr-3">
                      <span className="chip" style={{ background: colors.colorOf(row.category) }}>
                        {row.category}
                      </span>
                    </td>
                  )}
                  {first && (
                    <td rowSpan={span} className="pr-3 font-medium">
                      <span className="inline-flex items-center gap-2">
                        <CachedImage
                          src={avatar}
                          className="size-10 flex-none rounded-full bg-slate-200 object-cover"
                        />
                        {profileUrl ? (
                          // The channel page, straight from the planner's file.
                          // Rows without one aren't links — no guessed URLs.
                          <a
                            href={profileUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="hover:underline"
                          >
                            @{row.username} ↗
                          </a>
                        ) : (
                          <>@{row.username}</>
                        )}{' '}
                        {/* Single-platform KOLs keep the badge by the name;
                            grouped ones carry it per stat line instead. */}
                        {!grouped && (
                          <PlatformBadge platform={row.platform} label={row.platform_label} />
                        )}
                      </span>
                    </td>
                  )}
                  {/* Tier under the count it derives from — no extra column. Absent
                      (not "KOC") when followers are unknown; see tierOf(). */}
                  <td className="whitespace-nowrap pr-3 text-right">
                    {grouped && (
                      <span className="mr-1.5">
                        <PlatformBadge platform={row.platform} label={row.platform_label} />
                      </span>
                    )}
                    {fmt(row.followers)}
                    {(() => {
                      const tier = tierOf(row.followers);
                      return tier ? (
                        <span
                          className={`ml-1.5 rounded px-1.5 py-0.5 text-[10px] font-semibold ${tier.chip}`}
                        >
                          {tier.label}
                        </span>
                      ) : null;
                    })()}
                  </td>
                  {!hideMetrics && (
                    <>
                      <td className="pr-3 text-right font-semibold">{fmtFull(row.views)}</td>
                      <td className="pr-3 text-right">
                        {row.likesHidden ? (
                          <span
                            className="text-xs text-muted-foreground"
                            title="Instagram ซ่อนยอดไลก์ของโพสต์นี้ (ครีเอเตอร์เปิด hide like count)"
                          >
                            Hide
                          </span>
                        ) : (
                          fmtFull(row.likes)
                        )}
                      </td>
                      <td className="pr-3 text-right">{fmtFull(row.comments)}</td>
                      <td className="pr-3 text-right">{fmtFull(row.shares)}</td>
                      <td className="pr-3 text-right">{fmtFull(row.saves)}</td>
                      <td className="pr-3 text-right">{erText(row)}</td>
                    </>
                  )}
                  <td className="pr-3 text-muted-foreground">{row.posted || ''}</td>
                  {showMoney && first && (
                    <td rowSpan={span} className="pr-3 text-xs">
                      {kpiCell(row.username)}
                    </td>
                  )}
                  <td>
                    {row.url && (
                      <a href={row.url} target="_blank" rel="noopener noreferrer">
                        เปิด ↗
                      </a>
                    )}
                  </td>
                </tr>
              );
            }),
          )}
        </tbody>
      </table>
    </div>
  );
}
