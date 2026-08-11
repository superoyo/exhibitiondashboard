import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { FILTER_ALL } from '@kol/shared';

import { AppShell } from '@/components/layout/AppShell';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { SegmentedControl } from '@/components/common/SegmentedControl';
import { queryKeys } from '@/app/queryClient';
import { routes } from '@/config/routes';
import { apiErrorMessage } from '@/lib/axios';
import { buildCategoryColors } from '@/lib/colors';
import { getCampaign } from '@/features/campaigns/api/campaignsApi';
import { downloadReportCsv } from '@/features/report/lib/csv';
import {
  computeTotals,
  derive,
  distinctCategories,
  distinctPlatforms,
  sumBy,
} from '@/features/report/lib/metrics';
import {
  startCommentReclassify,
  startCommentRefresh,
} from '@/features/report/api/reportApi';
import {
  useCommentStatus,
  useComments,
  useReportData,
  useRefreshStatus,
  useResetCost,
} from '@/features/report/hooks/useReport';
import { useReportFilters } from '@/features/report/store/reportFiltersStore';
import { EngagementBreakdown, KpiRow } from './KpiRow';
import { Podium } from './Podium';
import { PostsTable } from './PostsTable';
import { CommentPanel } from './CommentPanel';
import { ReportActions } from './ReportActions';
import {
  CategoryDonut,
  CategoryErBar,
  EngagementStack,
  TopPostsBar,
} from './ReportCharts';

const FOOTER_NOTE =
  'ER = engagement(like+cmt+share+save)/views · โพสต์ที่ไม่มียอด views (เช่น รูปภาพบน Facebook/IG) ' +
  'ใช้ engagement/followers แทน (มี * กำกับ) · — = คำนวณไม่ได้ (ไม่มีทั้ง views และ followers) · ' +
  'ข้อมูลดึงจากลิงก์โพสต์แคมเปญผ่าน Apify (เฉพาะ KOL ที่ active) · กด Refresh Data เพื่ออัปเดต';

export function ReportView({
  campaign,
  viewOnly,
  influencerView = false,
}: {
  campaign: string;
  /** Client-facing mode: stats only, every control hidden. */
  viewOnly: boolean;
  /**
   * Influencer-facing mode (/vi/): a list of who has posted and who has not.
   * Drops the KPI summary, the engagement breakdown and every chart — those
   * are campaign performance, which is the client's report, not the
   * influencers'.
   */
  influencerView?: boolean;
}) {
  const [info, setInfo] = useState('');

  const meta = useQuery({
    queryKey: queryKeys.campaigns.detail(campaign),
    queryFn: () => getCampaign(campaign),
    enabled: Boolean(campaign),
  });

  const report = useReportData(campaign);
  const refreshStatus = useRefreshStatus(campaign, !viewOnly);
  const resetCost = useResetCost(campaign);
  const comments = useComments(campaign, !viewOnly);
  const commentStatus = useCommentStatus(campaign, !viewOnly);

  const filters = useReportFilters();

  // Filters are module-level state, so clear them when the campaign changes —
  // otherwise a category from the previous report leaks in and shows an empty
  // podium for no visible reason.
  useEffect(() => {
    filters.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [campaign]);

  // Memoised so the empty-array fallback doesn't produce a new identity on every
  // render and invalidate every downstream useMemo.
  const records = useMemo(() => report.data?.records ?? [], [report.data?.records]);
  const allRows = useMemo(() => derive(records), [records]);

  // Two-level grouping only makes sense when big groups exist AND differ from
  // the category; otherwise the filter row is hidden entirely.
  const bigGroups = useMemo(
    () => [...new Set(allRows.map((r) => r.biggroup).filter(Boolean))],
    [allRows],
  );
  const twoLevel =
    bigGroups.length > 1 && allRows.some((r) => r.biggroup && r.biggroup !== r.category);

  const rows = useMemo(() => {
    if (!twoLevel || filters.bigGroup === FILTER_ALL) return allRows;
    return allRows.filter((r) => r.biggroup === filters.bigGroup);
  }, [allRows, twoLevel, filters.bigGroup]);

  // Influencer view splits the table by whether a post link exists.
  const activeRows = useMemo(() => rows.filter((r) => r.url), [rows]);
  const waitingRows = useMemo(() => rows.filter((r) => !r.url), [rows]);

  const colors = useMemo(() => buildCategoryColors(distinctCategories(rows)), [rows]);
  const totals = useMemo(() => computeTotals(rows), [rows]);
  const byKind = useMemo(
    () => ({
      likes: sumBy(rows, 'likes'),
      comments: sumBy(rows, 'comments'),
      shares: sumBy(rows, 'shares'),
      saves: sumBy(rows, 'saves'),
    }),
    [rows],
  );

  // Surface refresh progress in the same status line the actions write to.
  useEffect(() => {
    const state = refreshStatus.data;
    if (!state) return;
    if (state.status === 'running') setInfo(state.message || 'กำลังดึงข้อมูล…');
    else if (state.status === 'success')
      setInfo(
        `✅ ${state.message || 'อัปเดตแล้ว'}${state.cost_usd ? ` · $${state.cost_usd}` : ''}`,
      );
    else if (state.status === 'failed') setInfo(`⚠️ ${state.message || 'ล้มเหลว'}`);
  }, [refreshStatus.data]);

  // Reload the data once a run finishes successfully.
  const refreshDone = refreshStatus.data?.status === 'success';
  useEffect(() => {
    if (refreshDone) void report.refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshDone]);

  const commentsBusy = commentStatus.data?.status === 'running';

  // Reload the breakdown once a comment run finishes, and surface its progress
  // in the same status line everything else writes to.
  const commentsDone = commentStatus.data?.status === 'success';
  useEffect(() => {
    if (commentsDone) void comments.refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [commentsDone]);

  useEffect(() => {
    const state = commentStatus.data;
    if (!state || state.status === 'idle') return;
    if (state.status === 'running') setInfo(state.message || 'กำลังดึงคอมเมนต์…');
    else if (state.status === 'success')
      setInfo(`✅ ${state.message}${state.cost_usd ? ` · $${state.cost_usd}` : ''}`);
    else if (state.status === 'failed') setInfo(`⚠️ ${state.message}`);
  }, [commentStatus.data]);

  async function handleRefreshComments() {
    // Spelled out because this is the only action billed per COMMENT — the
    // team should see the rate before spending, not after.
    if (
      !window.confirm(
        'ดึงคอมเมนต์ของทุกโพสต์ในแคมเปญนี้?\n\n' +
          'คิดเงินตามจำนวนคอมเมนต์จริง — TikTok $0.50 / Facebook $1.40 ต่อ 1,000 คอมเมนต์\n' +
          'แยกจากปุ่ม Refresh Data และไม่ทำงานเองอัตโนมัติ',
      )
    )
      return;
    try {
      await startCommentRefresh(campaign);
      setInfo('เริ่มดึงคอมเมนต์แล้ว…');
      void commentStatus.refetch();
    } catch (err) {
      setInfo(`⚠️ ${apiErrorMessage(err)}`);
    }
  }

  async function handleReclassifyComments() {
    if (
      !window.confirm(
        'จัดประเภทคอมเมนต์ที่เก็บไว้แล้วใหม่ทั้งหมด ด้วยกฎล่าสุด?\n\n' +
          'ไม่ดึงคอมเมนต์ใหม่ จึงไม่มีค่า Apify — มีแต่ค่า AI จัดประเภท (หลักสตางค์)',
      )
    )
      return;
    try {
      await startCommentReclassify(campaign);
      setInfo('เริ่มจัดประเภทใหม่แล้ว…');
      void commentStatus.refetch();
    } catch (err) {
      setInfo(`⚠️ ${apiErrorMessage(err)}`);
    }
  }

  const campaignName = meta.data?.name ?? campaign;
  const emoji = meta.data?.emoji ?? '📊';
  const refreshing = refreshStatus.data?.status === 'running';

  const updatedAt = report.data?.refreshed_at
    ? new Date(report.data.refreshed_at).toLocaleString('th-TH')
    : '—';

  function handleResetCost() {
    if (!window.confirm('รีเซ็ตยอดค่าใช้จ่ายสะสมของแคมเปญนี้เป็น $0?')) return;
    resetCost.mutate();
  }

  const body = (
    <>
      <header className="mb-4">
        <div className="min-w-0">
          <h1 className="text-xl font-bold sm:text-3xl">
            {emoji} {campaignName} —{' '}
            {influencerView ? 'Campaign Influencer List' : 'Campaign Report'}
          </h1>
          <p className="text-sm text-muted-foreground">
            {meta.data?.subtitle || 'ข้อมูลจริงจาก TikTok/Facebook ผ่าน Apify'}
          </p>
        </div>

        {!viewOnly && (
          <div className="mt-3">
            <ReportActions
              campaign={campaign}
              campaignName={campaignName}
              refreshing={refreshing}
              commentsBusy={commentsBusy}
              commentCount={comments.data?.total ?? 0}
              onRefreshComments={() => void handleRefreshComments()}
              onReclassifyComments={() => void handleReclassifyComments()}
              onStatus={setInfo}
            />
            <div className="mt-1 text-xs text-muted-foreground">
              {info ||
                `อัปเดตล่าสุด: ${updatedAt} · ${report.data?.post_count ?? 0}/${report.data?.roster_count ?? 0} โพสต์มีข้อมูล`}
            </div>
            <div className="mt-1 text-xs">
              💸 ค่าใช้จ่ายสะสม:{' '}
              <b className="text-destructive">${(report.data?.cost_total ?? 0).toFixed(3)}</b> ·{' '}
              {report.data?.cost_count ?? 0} ครั้ง ·{' '}
              <button
                type="button"
                onClick={handleResetCost}
                className="text-muted-foreground underline"
              >
                รีเซ็ต
              </button>
            </div>
          </div>
        )}
      </header>

      {report.isError ? (
        <Card className="p-6 text-destructive">
          โหลดข้อมูลไม่สำเร็จ: {apiErrorMessage(report.error)}
        </Card>
      ) : report.isLoading ? (
        <Card className="p-8 text-center text-sm text-muted-foreground">กำลังโหลด…</Card>
      ) : records.length === 0 ? (
        <Card className="p-8 text-center">
          <div className="mb-2 text-4xl">📭</div>
          <div className="mb-1 font-semibold">ยังไม่มีรายชื่อ KOL ในแคมเปญนี้</div>
          <div className="mb-4 text-sm text-muted-foreground">
            เพิ่มรายชื่อ/ลิงก์โพสต์ในหน้า{' '}
            <a href={`${routes.roster}?campaign=${encodeURIComponent(campaign)}`}>แก้ไข KOL</a>{' '}
            แล้วกด Refresh Data
          </div>
        </Card>
      ) : (
        <>
          {twoLevel && (
            <SegmentedControl
              className="mb-4"
              label="กลุ่มใหญ่:"
              options={[FILTER_ALL, ...bigGroups].map((g) => ({ value: g, label: g }))}
              value={filters.bigGroup}
              onChange={filters.setBigGroup}
            />
          )}

          {!influencerView && (
            <>
              <KpiRow totals={totals} />

              <h2 className="mb-2 text-sm font-semibold text-muted-foreground">
                รายละเอียด Engagement (like + comment + share + save)
              </h2>
              <EngagementBreakdown totals={totals} byKind={byKind} />
            </>
          )}

          <Podium
            influencerView={influencerView}
            rows={rows}
            categories={colors.categories}
            platforms={distinctPlatforms(rows)}
            colors={colors}
            category={filters.category}
            platform={filters.platform}
            metric={filters.metric}
            onCategoryChange={filters.setCategory}
            onPlatformChange={filters.setPlatform}
            onMetricChange={filters.setMetric}
          />

          {!influencerView && (
            <div className="mb-5 grid grid-cols-1 gap-4 lg:grid-cols-2">
              <Card>
                <CardContent className="p-4">
                  <h3 className="mb-1 font-semibold">Views ตามหมวด KOL</h3>
                  <CategoryDonut rows={rows} colors={colors} />
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <h3 className="mb-1 font-semibold">Engagement Rate ตามหมวด</h3>
                  <CategoryErBar rows={rows} colors={colors} />
                </CardContent>
              </Card>
              <Card className="lg:col-span-2">
                <CardContent className="p-4">
                  <h3 className="mb-1 font-semibold">
                    Engagement แยกชนิดตามหมวด (like / comment / share / save)
                  </h3>
                  <EngagementStack rows={rows} colors={colors} />
                </CardContent>
              </Card>
              <Card className="lg:col-span-2">
                <CardContent className="p-4">
                  <h3 className="mb-1 font-semibold">Top 10 โพสต์ (ตาม Views)</h3>
                  <TopPostsBar rows={rows} colors={colors} />
                </CardContent>
              </Card>
            </div>
          )}

          {/* Comment breakdown. Hidden from the client-facing view along with
              the other controls, and rendered from stored rows only — opening
              the report never triggers a scrape. */}
          {!influencerView && comments.data ? (
            <div className="mb-5">
              <CommentPanel campaign={campaign} data={comments.data} />
            </div>
          ) : null}

          {influencerView ? (
            // Split by whether a post link exists: "Active" has posted,
            // "Waiting" has not. That single question is what an influencer
            // opens this link to answer.
            <>
              <Card>
                <CardContent className="p-4">
                  <h3 className="mb-2 font-semibold">Active</h3>
                  <PostsTable rows={activeRows} colors={colors} hideMetrics />
                </CardContent>
              </Card>
              <Card className="mt-4">
                <CardContent className="p-4">
                  <h3 className="mb-2 font-semibold">Waiting</h3>
                  <PostsTable rows={waitingRows} colors={colors} hideMetrics />
                </CardContent>
              </Card>
            </>
          ) : (
            <Card>
              <CardContent className="p-4">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <h3 className="font-semibold">รายโพสต์ทั้งหมด (คลิกหัวคอลัมน์เพื่อจัดเรียง)</h3>
                  <Button
                    variant="outline"
                    size="sm"
                    className="rounded-full"
                    onClick={() => downloadReportCsv(rows, campaignName)}
                  >
                    ⬇ ดาวน์โหลด CSV
                  </Button>
                </div>
                <PostsTable rows={rows} colors={colors} />
              </CardContent>
            </Card>
          )}

          {!influencerView && (
            <footer className="mt-5 text-xs text-muted-foreground">{FOOTER_NOTE}</footer>
          )}
        </>
      )}
    </>
  );

  // View-only pages hide the navbar entirely — clients get no route into the
  // rest of the app.
  if (viewOnly) {
    return <div className="mx-auto max-w-7xl px-3 py-5 sm:px-5">{body}</div>;
  }

  return (
    <AppShell tabs={[{ to: routes.home, label: '← Home', end: true }]} className="max-w-7xl py-5">
      {body}
    </AppShell>
  );
}
