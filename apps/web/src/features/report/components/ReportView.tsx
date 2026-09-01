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
  getAdvisorStatus,
  getViewCommercial,
  runAdvisor,
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
import { KpiLine, PostsTable, type CommercialByUser } from './PostsTable';
import { useRoster } from '@/features/roster/hooks/useRoster';
import { getGroupKpis } from '@/features/roster/api/rosterApi';
import { AdvisorPanel } from './AdvisorPanel';
import { CommentPanel } from './CommentPanel';
import { ReportActions } from './ReportActions';
import { CategoryDonut, CategoryErBar, EngagementStack, TopPostsBar } from './ReportCharts';

const FOOTER_NOTE =
  'ER = engagement(like+cmt+share+save)/views · โพสต์ที่ไม่มียอด views (เช่น รูปภาพบน Facebook/IG) ' +
  'ใช้ engagement/followers แทน (มี * กำกับ) · — = คำนวณไม่ได้ (ไม่มีทั้ง views และ followers) · ' +
  'ข้อมูลดึงจากลิงก์โพสต์แคมเปญผ่าน Apify (เฉพาะ KOL ที่ active) · กด Refresh Data เพื่ออัปเดต';

/** Thai labels for the job kinds the server records spend under. */
const COST_LABELS: Record<string, string> = {
  refresh: 'อัปเดตสถิติ',
  comments: 'วิเคราะห์คอมเมนต์',
  // tiein is step 1 of the 📥 PowerPoint button, not a button of its own —
  // labelled so this line reads as part of the deck's production cost.
  tiein: 'หา tie-in shot (ปุ่ม PowerPoint)',
  profiles: 'ดึงรูปโปรไฟล์',
  advisor: 'Performance Analysis (ค่า AI)',
};

/**
 * Which button spent what. The server used to add every charge into one number,
 * so a campaign's total could not be attributed to any action.
 *
 * Runs recorded before the split are shown as their own line rather than
 * divided up by guesswork — a made-up attribution is worse than an honest
 * "cannot tell".
 */
function CostBreakdown({
  total,
  byKind,
}: {
  total: number;
  byKind: Record<string, { total: number; count: number }>;
}) {
  const rows = Object.entries(byKind)
    .filter(([kind]) => COST_LABELS[kind])
    .sort((a, b) => b[1].total - a[1].total);
  if (rows.length === 0) return null;

  const split = rows.reduce((sum, [, v]) => sum + v.total, 0);
  const legacy = Math.max(0, total - split);

  return (
    <div className="mt-1 space-y-0.5 border-l-2 border-brand-400 pl-2">
      {rows.map(([kind, v]) => (
        <div key={kind} className="flex gap-2 text-[11px] text-muted-foreground">
          <span className="w-44 shrink-0">{COST_LABELS[kind]}</span>
          <span className="w-16 text-right tabular-nums">${v.total.toFixed(3)}</span>
          <span className="tabular-nums">{v.count} ครั้ง</span>
        </div>
      ))}
      {legacy > 0.0005 ? (
        <div className="flex gap-2 text-[11px] text-muted-foreground/70">
          <span className="w-44 shrink-0">ก่อนหน้านี้ (แยกไม่ได้)</span>
          <span className="w-16 text-right tabular-nums">${legacy.toFixed(3)}</span>
        </div>
      ) : null}
    </div>
  );
}

/**
 * "ลงงานแล้ว X/Y คน" chip beside the posts-table heading.
 *
 * Counts PEOPLE, not rows: the table has one row per KOL-platform, so a KOL on
 * TikTok+Instagram is two rows but one person. "Posted" = at least one of their
 * rows carries a post link — the same split the influencer view uses for its
 * Active/Waiting sections. Counted from the rows currently shown, so filtering
 * to one big group makes the chip answer for that group.
 */
function PostedCount({ rows }: { rows: { username: string; url: string }[] }) {
  const everyone = new Set(rows.map((r) => r.username));
  const posted = new Set(rows.filter((r) => r.url).map((r) => r.username));
  if (everyone.size === 0) return null;
  const done = posted.size === everyone.size;
  return (
    <span
      className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
        done ? 'bg-emerald-50 text-state-ok' : 'bg-brand-200 text-[#8a6a00]'
      }`}
    >
      {done ? '✅' : '⏳'} ลงงานแล้ว {posted.size}/{everyone.size} คน
    </span>
  );
}

export function ReportView({
  campaign,
  viewOnly,
  influencerView = false,
  viewToken = '',
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
  /**
   * The token from a public `/v/:viewToken` link. Present only when there is no
   * session, which is what the comment reads switch on — `viewOnly` alone does
   * not imply that, because `/c/<key>?view=1` is the team previewing the client
   * layout while logged in.
   */
  viewToken?: string;
}) {
  const [info, setInfo] = useState('');

  const meta = useQuery({
    queryKey: queryKeys.campaigns.detail(campaign),
    queryFn: () => getCampaign(campaign),
    enabled: Boolean(campaign),
  });

  const report = useReportData(campaign);
  // Commercial fields (selling price / boost budget / KPI). The client link
  // shows them too since 2026-09-01 (team decision) — but they still never ride
  // on the open, campaign-key-addressed report data. Logged-in views (internal
  // and the ?view=1 preview) read the roster endpoints; a /v/ token link reads
  // the token-addressed endpoint, exactly like the comment panel does.
  // The influencer list (/vi/) shows none of this — that link answers "have I
  // posted", and its readers are the KOLs themselves.
  const roster = useRoster('report', campaign, !influencerView && !viewToken);
  const groupKpis = useQuery({
    queryKey: ['roster', 'groupkpi', campaign],
    queryFn: () => getGroupKpis(campaign),
    enabled: !influencerView && !viewToken && Boolean(campaign),
  });
  const viewCommercial = useQuery({
    queryKey: ['report', 'view-commercial', viewToken],
    queryFn: () => getViewCommercial(viewToken),
    enabled: !influencerView && Boolean(viewToken),
  });
  const commercial = useMemo(() => {
    if (viewToken) return viewCommercial.data?.kols ?? {};
    const map: CommercialByUser = {};
    for (const k of roster.data ?? []) {
      if (k.cost_thb != null || k.boost_thb != null || (k.kpis ?? []).length > 0) {
        map[k.username.toLowerCase()] = {
          cost_thb: k.cost_thb,
          boost_thb: k.boost_thb,
          kpis: k.kpis ?? [],
        };
      }
    }
    return map;
  }, [viewToken, viewCommercial.data, roster.data]);
  const groupKpiData = (viewToken ? viewCommercial.data?.group_kpis : groupKpis.data) ?? {};
  // Columns appear only when at least one KOL actually carries a value —
  // a campaign without planner data keeps its familiar table.
  const hasCommercial = !influencerView && Object.keys(commercial).length > 0;

  const refreshStatus = useRefreshStatus(campaign, !viewOnly);
  const resetCost = useResetCost(campaign);
  // The client's report shows the comment analysis too. On a token link it reads
  // through the token endpoints; on the logged-in `?view=1` preview the ordinary
  // authenticated ones still work.
  const comments = useComments(campaign, !influencerView, viewToken);
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

  // Performance Analysis — triggered from the top action bar, displayed by the
  // panel below. One Opus call per press; status polled like the other jobs.
  const advisorStatus = useQuery({
    queryKey: ['report', 'advisor-status', campaign],
    queryFn: () => getAdvisorStatus(campaign),
    enabled: !viewOnly && Boolean(campaign),
    refetchInterval: (q) => (q.state.data?.status === 'running' ? 4000 : false),
  });
  const advisorBusy = advisorStatus.data?.status === 'running';

  async function handleRunAdvisor() {
    try {
      await runAdvisor(campaign);
      setInfo('📈 เริ่มวิเคราะห์ Performance…');
      await advisorStatus.refetch();
    } catch (error) {
      setInfo(`⚠️ ${apiErrorMessage(error)}`);
    }
  }

  useEffect(() => {
    const state = advisorStatus.data;
    if (!state || state.status === 'idle') return;
    if (state.status === 'running') setInfo(`📈 ${state.message || 'กำลังวิเคราะห์…'}`);
    else if (state.status === 'failed') setInfo(`⚠️ ${state.message || 'วิเคราะห์ไม่สำเร็จ'}`);
    else if (state.status === 'success' && state.message) setInfo(`✅ ${state.message}`);
  }, [advisorStatus.data]);

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
              advisorBusy={advisorBusy}
              onRunAdvisor={() => void handleRunAdvisor()}
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
              <CostBreakdown
                total={report.data?.cost_total ?? 0}
                byKind={report.data?.cost_by_kind ?? {}}
              />
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

          {/* Performance advisor — grades per posted KOL. Shown to the client
              too (its v2 output is engagement figures only; the prompt bans
              money in it) — the analysis is part of what the client pays for.
              Off in the influencer view: KOLs don't get each other's grades. */}
          {!influencerView ? (
            <div className="mb-5">
              <AdvisorPanel
                campaign={campaign}
                running={advisorBusy}
                statusMessage={advisorStatus.data?.message}
                viewOnly={viewOnly}
                viewToken={viewToken}
              />
            </div>
          ) : null}

          {/* Comment breakdown. Shown on the client report as well as ours —
              it is analysis the client is paying for. Rendered from stored rows
              only, so opening the report never triggers a scrape, and the panel
              drops its own internal controls when a view token is present.
              Still off in the influencer view: that link answers "have I
              posted", not how the campaign performed. */}
          {!influencerView && comments.data ? (
            <div className="mb-5">
              <CommentPanel
                campaign={campaign}
                campaignName={campaignName}
                data={comments.data}
                viewOnly={viewOnly}
                viewToken={viewToken}
              />
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
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex min-w-0 flex-wrap items-center gap-2">
                    <h3 className="font-semibold">รายโพสต์ทั้งหมด (คลิกหัวคอลัมน์เพื่อจัดเรียง)</h3>
                    <PostedCount rows={rows} />
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    className="rounded-full"
                    onClick={() => downloadReportCsv(rows, campaignName)}
                  >
                    ⬇ ดาวน์โหลด CSV
                  </Button>
                </div>
                {/* Group-total KPIs ("7M Imp across Micro Package") — a target
                    that belongs to the whole group, checked against the SUM of
                    that group's rows. On the client link too, like the columns. */}
                {Object.keys(groupKpiData).length > 0 ? (
                  <div className="mb-3 space-y-1 rounded-lg border border-brand-400 bg-brand-200/40 p-2 text-xs">
                    <div className="font-semibold">📦 KPI รายกลุ่ม</div>
                    {Object.entries(groupKpiData).map(([g, kpis]) => {
                      const members = allRows.filter((r) => r.biggroup === g || r.category === g);
                      const totals = {
                        views: members.reduce((s, r) => s + r.views, 0),
                        engagement: members.reduce((s, r) => s + r.engagement, 0),
                      };
                      return (
                        <div key={g} className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                          <span className="chip" style={{ background: colors.colorOf(g) }}>
                            {g}
                          </span>
                          {members.length === 0 ? (
                            <span className="text-amber-700">
                              ⚠️ ไม่มี KOL ในกลุ่มชื่อนี้แล้ว
                              {viewOnly ? '' : ' (กลุ่มอาจถูกเปลี่ยนชื่อ — แก้ได้ในหน้ารายชื่อ)'}
                            </span>
                          ) : (
                            kpis.map((k) => (
                              <KpiLine key={k.metric + k.target} kpi={k} totals={totals} />
                            ))
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : null}
                <PostsTable
                  rows={rows}
                  colors={colors}
                  commercial={hasCommercial ? commercial : undefined}
                />
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
