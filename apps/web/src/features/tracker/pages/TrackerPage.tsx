import { useMemo, useState } from 'react';
import { TREND_METRICS, type TrendMetric } from '@kol/shared';

import { AppShell } from '@/components/layout/AppShell';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { routes } from '@/config/routes';
import { apiErrorMessage } from '@/lib/axios';
import { useDebounce } from '@/hooks/useDebounce';
import { GroupChips } from '@/features/tracker/components/GroupChips';
import { KolDetailView } from '@/features/tracker/components/KolDetailView';
import { SummaryKpis } from '@/features/tracker/components/SummaryKpis';
import { SummaryTable } from '@/features/tracker/components/SummaryTable';
import {
  FollowersScatter,
  GroupDonut,
  TopKolBar,
  TrendChart,
} from '@/features/tracker/components/TrackerCharts';
import { useHashKol } from '@/features/tracker/hooks/useHashKol';
import { useHealth, useKolDetail, useSummary, useTrend } from '@/features/tracker/hooks/useTracker';

const TRACKER_TABS = [
  { to: routes.home, label: '← Home', end: true },
  { to: `${routes.roster}?campaign=__tracker`, label: 'แก้ไข KOL' },
];

const selectClass =
  'rounded-lg border border-border bg-white px-3 py-1.5 text-sm ' +
  'focus-visible:border-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand';

export default function TrackerPage() {
  const [group, setGroup] = useState('All');
  const [date, setDate] = useState('latest');
  const [search, setSearch] = useState('');
  const [metric, setMetric] = useState<TrendMetric>('views');

  const query = useDebounce(search).trim().toLowerCase();

  const health = useHealth();
  const summary = useSummary(date, group);
  const trend = useTrend(metric, group);

  const { username: detailUser, open: openDetail, close: closeDetail } = useHashKol();
  const detail = useKolDetail(detailUser);

  // Search filters client-side, so it does not re-hit the API per keystroke.
  const filteredKols = useMemo(() => {
    const kols = summary.data?.kols ?? [];
    if (!query) return kols;
    return kols.filter((k) => `${k.display}${k.username}`.toLowerCase().includes(query));
  }, [summary.data?.kols, query]);

  const availableDates = summary.data?.available_dates ?? [];
  const dataAsOf = health.data?.latest_scrape_date;
  const lastRun = health.data?.last_run;

  return (
    <AppShell tabs={TRACKER_TABS} className="max-w-7xl">
      <header className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-bold sm:text-2xl">📊 KOL TikTok Tracker</h1>
          <p className="text-xs text-muted-foreground sm:text-sm">
            Sahagroup Fair 2026 · Nano–Micro 41 KOL
          </p>
        </div>
        <div className="text-right text-xs text-muted-foreground sm:text-sm">
          <div>
            {health.isLoading ? 'กำลังโหลด…' : dataAsOf ? `ข้อมูล ณ ${dataAsOf}` : 'ยังไม่มีข้อมูล'}
          </div>
          {lastRun && (
            <div className="mt-0.5">
              รันล่าสุด:{' '}
              <span className={lastRun.status === 'success' ? 'text-state-ok' : 'text-state-error'}>
                {lastRun.status}
              </span>
              {lastRun.cost_usd != null && ` · $${lastRun.cost_usd}`}
            </div>
          )}
        </div>
      </header>

      {detailUser ? (
        <KolDetailView
          detail={detail.data}
          isLoading={detail.isLoading}
          isError={detail.isError}
          onBack={closeDetail}
        />
      ) : (
        <>
          <Card className="mb-4">
            <CardContent className="flex flex-wrap items-center gap-2 p-3">
              <GroupChips value={group} onChange={setGroup} />
              <div className="flex-1" />
              <Input
                className="h-9 w-full sm:w-48"
                placeholder="🔍 ค้นหา KOL…"
                aria-label="ค้นหา KOL"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              <select
                className={selectClass}
                aria-label="เลือกวันที่ข้อมูล"
                value={availableDates.includes(date) ? date : (summary.data?.date ?? '')}
                onChange={(e) => setDate(e.target.value)}
              >
                {availableDates.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </CardContent>
          </Card>

          {summary.isError ? (
            <Card className="p-6 text-destructive">
              โหลดไม่สำเร็จ: {apiErrorMessage(summary.error)}
            </Card>
          ) : (
            <>
              <SummaryKpis kpis={summary.data?.kpis ?? {}} />

              <div className="mb-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
                <Card>
                  <CardContent className="p-3">
                    <div className="mb-1 flex items-center justify-between">
                      <h3 className="text-sm font-semibold">แนวโน้มรายวัน (7-day rolling)</h3>
                      <select
                        className="rounded border border-border bg-white px-2 py-1 text-xs"
                        aria-label="เลือกตัวชี้วัดแนวโน้ม"
                        value={metric}
                        onChange={(e) => setMetric(e.target.value as TrendMetric)}
                      >
                        {TREND_METRICS.map((m) => (
                          <option key={m} value={m}>
                            {m === 'views'
                              ? 'Views'
                              : m === 'engagement'
                                ? 'Engagement'
                                : 'Followers'}
                          </option>
                        ))}
                      </select>
                    </div>
                    <TrendChart series={trend.data?.series ?? []} metric={metric} />
                  </CardContent>
                </Card>

                <Card>
                  <CardContent className="p-3">
                    <h3 className="mb-1 text-sm font-semibold">สัดส่วน Views ตามกลุ่ม</h3>
                    <GroupDonut kols={filteredKols} />
                  </CardContent>
                </Card>

                <Card>
                  <CardContent className="p-3">
                    <h3 className="mb-1 text-sm font-semibold">Top 10 KOL by Views</h3>
                    <TopKolBar kols={filteredKols} />
                  </CardContent>
                </Card>

                <Card>
                  <CardContent className="p-3">
                    <h3 className="mb-1 text-sm font-semibold">Followers vs Views (log scale)</h3>
                    <FollowersScatter kols={filteredKols} />
                  </CardContent>
                </Card>
              </div>

              <Card>
                <CardContent className="p-3">
                  <h3 className="mb-2 text-sm font-semibold">
                    สรุปรายคน <span className="text-muted-foreground">({filteredKols.length})</span>
                  </h3>
                  <SummaryTable kols={filteredKols} onSelect={openDetail} />
                </CardContent>
              </Card>
            </>
          )}
        </>
      )}

      <footer className="mt-6 text-center text-xs text-muted-foreground">
        ตัวเลขเป็น snapshot ณ เวลาที่ดึงข้อมูล · auto-scrape ทุกเช้า 05:00 น. (เวลาไทย)
      </footer>
    </AppShell>
  );
}
