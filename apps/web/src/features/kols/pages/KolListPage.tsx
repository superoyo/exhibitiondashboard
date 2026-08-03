import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { AppShell } from '@/components/layout/AppShell';
import { CachedImage } from '@/components/common/CachedImage';
import { PlatformBadge } from '@/components/common/PlatformBadge';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { queryKeys } from '@/app/queryClient';
import { routes } from '@/config/routes';
import { apiErrorMessage } from '@/lib/axios';
import { fmt } from '@/lib/format';
import { cn } from '@/lib/utils';
import {
  getKolDirectory,
  type KolCampaignEntry,
  type KolDirectoryEntry,
} from '@/features/kols/api/kolDirectoryApi';

/** Sortable columns. `engagement` is derived, so it is not a field on the row. */
type SortKey = 'followers' | 'campaign_count' | 'posts' | 'views' | 'engagement' | 'last_posted';

const COLUMNS: Array<{ key?: SortKey; label: string; align?: 'right' }> = [
  { label: 'KOL' },
  { label: 'แพลตฟอร์ม' },
  { key: 'followers', label: 'Followers', align: 'right' },
  { key: 'campaign_count', label: 'แคมเปญ', align: 'right' },
  { key: 'posts', label: 'โพสต์', align: 'right' },
  { key: 'views', label: 'Views รวม', align: 'right' },
  { key: 'engagement', label: 'Engagement รวม', align: 'right' },
  { key: 'last_posted', label: 'ลงงานล่าสุด' },
];

const engagementOf = (k: KolDirectoryEntry | KolCampaignEntry) =>
  (k.likes ?? 0) + (k.comments ?? 0) + (k.shares ?? 0) + (k.saves ?? 0);

/** Thai short date, or an em dash when the KOL has never posted. */
function dateText(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
  return d.toLocaleDateString('th-TH', { year: '2-digit', month: 'short', day: 'numeric' });
}

/**
 * `/kol-list` — the team's record of every KOL ever used, across all campaigns.
 *
 * Sorted by campaign count first: the question this page answers is "have we
 * worked with this person before, and how did it go", so the people used most
 * belong at the top.
 */
export default function KolListPage() {
  const [query, setQuery] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('campaign_count');
  const [descending, setDescending] = useState(true);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const directory = useQuery({
    queryKey: queryKeys.kols.directory,
    queryFn: getKolDirectory,
  });

  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const list = (directory.data ?? []).filter(
      (k) => !needle || k.username.includes(needle) || k.display.toLowerCase().includes(needle),
    );
    return [...list].sort((a, b) => {
      const va = sortKey === 'engagement' ? engagementOf(a) : (a[sortKey] ?? '');
      const vb = sortKey === 'engagement' ? engagementOf(b) : (b[sortKey] ?? '');
      if (typeof va === 'string' || typeof vb === 'string') {
        return descending
          ? String(vb).localeCompare(String(va))
          : String(va).localeCompare(String(vb));
      }
      return descending ? Number(vb) - Number(va) : Number(va) - Number(vb);
    });
  }, [directory.data, query, sortKey, descending]);

  function toggleSort(key: SortKey) {
    if (key === sortKey) setDescending((d) => !d);
    else {
      setSortKey(key);
      setDescending(true);
    }
  }

  function toggleRow(username: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(username)) next.delete(username);
      else next.add(username);
      return next;
    });
  }

  return (
    <AppShell
      tabs={[
        { to: routes.home, label: 'Home', end: true },
        { to: routes.kolList, label: 'KOL List' },
        { to: routes.settings, label: 'Apify Token' },
      ]}
    >
      <header className="mb-4">
        <h1 className="text-xl font-bold sm:text-2xl">👥 KOL List — ทำเนียบ KOL ทุกแคมเปญ</h1>
        <p className="text-sm text-muted-foreground">
          บันทึกว่าเคยใช้งานใครในแคมเปญไหนบ้าง · คลิกที่รายชื่อเพื่อดู stat ย้อนหลังรายแคมเปญ
        </p>
      </header>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Input
          className="max-w-[380px]"
          placeholder="🔍 ค้นหาชื่อ / @handle …"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <span className="text-sm text-muted-foreground">
          {directory.isSuccess ? `${rows.length} คน · รวมทุกแคมเปญ` : ''}
        </span>
      </div>

      <Card>
        <CardContent className="p-4">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  {COLUMNS.map((col) => (
                    <th
                      key={col.label}
                      onClick={col.key ? () => toggleSort(col.key!) : undefined}
                      aria-sort={
                        col.key && sortKey === col.key
                          ? descending
                            ? 'descending'
                            : 'ascending'
                          : 'none'
                      }
                      className={cn(
                        'whitespace-nowrap py-2 pr-3 font-normal',
                        col.key && 'cursor-pointer select-none',
                        col.align === 'right' && 'text-right',
                      )}
                    >
                      {col.label}
                      {col.key && sortKey === col.key && (descending ? ' ▼' : ' ▲')}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {directory.isLoading && (
                  <tr>
                    <td colSpan={COLUMNS.length} className="py-8 text-center text-muted-foreground">
                      กำลังโหลด…
                    </td>
                  </tr>
                )}
                {directory.isError && (
                  <tr>
                    <td colSpan={COLUMNS.length} className="py-8 text-center text-destructive">
                      โหลดข้อมูลไม่สำเร็จ: {apiErrorMessage(directory.error)}
                    </td>
                  </tr>
                )}
                {directory.isSuccess && rows.length === 0 && (
                  <tr>
                    <td colSpan={COLUMNS.length} className="py-8 text-center text-muted-foreground">
                      ไม่พบรายชื่อ
                    </td>
                  </tr>
                )}
                {rows.map((kol) => (
                  <KolRow
                    key={kol.username}
                    kol={kol}
                    open={expanded.has(kol.username)}
                    onToggle={() => toggleRow(kol.username)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </AppShell>
  );
}

function KolRow({
  kol,
  open,
  onToggle,
}: {
  kol: KolDirectoryEntry;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <>
      <tr
        onClick={onToggle}
        className="cursor-pointer border-b border-border hover:bg-slate-50"
        aria-expanded={open}
      >
        <td className="py-2 pr-3">
          <div className="flex items-center gap-2">
            {kol.avatar ? (
              <CachedImage src={kol.avatar} className="size-[34px] rounded-full object-cover" />
            ) : (
              <div className="flex size-[34px] items-center justify-center rounded-full bg-slate-200 font-bold text-slate-600">
                {(kol.display || kol.username).charAt(0).toUpperCase()}
              </div>
            )}
            <div>
              <div className="font-semibold">{kol.display}</div>
              <div className="text-xs text-muted-foreground">@{kol.username}</div>
            </div>
          </div>
        </td>
        <td className="pr-3">
          {kol.platforms.map((p) => (
            <PlatformBadge key={p} platform={p} className="mr-0.5" />
          ))}
        </td>
        <td className="pr-3 text-right">{fmt(kol.followers)}</td>
        <td className="pr-3 text-right font-semibold">{kol.campaign_count}</td>
        <td className="pr-3 text-right">{kol.posts}</td>
        <td className="pr-3 text-right font-semibold">{fmt(kol.views)}</td>
        <td className="pr-3 text-right">{fmt(engagementOf(kol))}</td>
        <td className="pr-3">{dateText(kol.last_posted)}</td>
      </tr>

      {open && (
        <tr className="border-b border-border">
          <td colSpan={COLUMNS.length} className="bg-white px-2 py-3">
            {kol.campaigns.map((c) => (
              <CampaignDetail key={c.key} campaign={c} />
            ))}
          </td>
        </tr>
      )}
    </>
  );
}

/** One campaign's totals for this KOL — the "how did it go" half of the page. */
function CampaignDetail({ campaign: c }: { campaign: KolCampaignEntry }) {
  const engagement = engagementOf(c);
  const er = c.views ? `${((engagement / c.views) * 100).toFixed(2)}%` : '—';

  return (
    <div className="mb-2 rounded-[14px] border border-border bg-slate-50 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="font-semibold">
          {c.emoji} {c.name}{' '}
          {c.category && (
            <span className="text-xs font-normal text-muted-foreground">· {c.category}</span>
          )}
        </div>
        <a href={routes.campaign(c.key)} className="text-xs text-blue-600">
          เปิดรายงาน ↗
        </a>
      </div>
      <div className="mt-1 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-700">
        <span>
          {c.platforms.map((p) => (
            <PlatformBadge key={p} platform={p} className="mr-0.5" />
          ))}
        </span>
        <span>
          โพสต์ <b>{c.posts}</b>
        </span>
        <span>
          Views <b>{fmt(c.views)}</b>
        </span>
        <span>
          ❤️ <b>{fmt(c.likes)}</b>
        </span>
        <span>
          💬 <b>{fmt(c.comments)}</b>
        </span>
        <span>
          🔁 <b>{fmt(c.shares)}</b>
        </span>
        <span>
          🔖 <b>{fmt(c.saves)}</b>
        </span>
        <span>
          ER <b>{er}</b>
        </span>
        <span>ลงงาน {dateText(c.last_posted)}</span>
      </div>
    </div>
  );
}
