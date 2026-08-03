import { useMemo } from 'react';
import { TRACKER_GROUP_COLORS, type KolDetail } from '@kol/shared';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { EChart } from '@/components/common/EChart';
import { AXIS_THEME, type EChartsOption } from '@/lib/echarts';
import { fmtCompact } from '@/lib/format';

/** Followers (right axis) against 7-day views (left axis). */
function DetailTrend({ detail }: { detail: KolDetail }) {
  const option = useMemo<EChartsOption>(() => {
    const dates = detail.trend.map((p) => p.date);
    return {
      tooltip: { trigger: 'axis', valueFormatter: (v) => fmtCompact(v as number) },
      legend: { textStyle: { color: '#475569' }, top: 0 },
      grid: { left: 55, right: 55, top: 30, bottom: 25 },
      xAxis: { type: 'category', data: dates, ...AXIS_THEME },
      // Two independent scales: followers dwarf weekly views, so a shared axis
      // would flatten the views line into the baseline.
      yAxis: [
        { type: 'value', ...AXIS_THEME },
        { type: 'value', ...AXIS_THEME },
      ],
      series: [
        {
          name: 'Followers',
          type: 'line',
          smooth: true,
          yAxisIndex: 1,
          data: detail.trend.map((p) => p.followers),
          lineStyle: { color: '#d97706' },
          itemStyle: { color: '#d97706' },
        },
        {
          name: 'Views (7d)',
          type: 'line',
          smooth: true,
          data: detail.trend.map((p) => p.views_7d),
          lineStyle: { color: '#2563eb' },
          itemStyle: { color: '#2563eb' },
        },
      ],
    };
  }, [detail]);

  return <EChart option={option} height={280} ariaLabel="Followers และ Views" />;
}

function DetailEngagement({ detail }: { detail: KolDetail }) {
  const option = useMemo<EChartsOption>(() => {
    return {
      tooltip: {
        trigger: 'axis',
        valueFormatter: (v) => (v == null ? '–' : `${((v as number) * 100).toFixed(2)}%`),
      },
      grid: { left: 55, right: 20, top: 15, bottom: 25 },
      xAxis: { type: 'category', data: detail.trend.map((p) => p.date), ...AXIS_THEME },
      yAxis: {
        type: 'value',
        ...AXIS_THEME,
        axisLabel: { color: '#64748b', formatter: (v: number) => `${(v * 100).toFixed(1)}%` },
      },
      series: [
        {
          type: 'line',
          smooth: true,
          data: detail.trend.map((p) => p.engagement_rate),
          lineStyle: { color: '#ec4899' },
          itemStyle: { color: '#ec4899' },
          areaStyle: { color: '#ec489922' },
        },
      ],
    };
  }, [detail]);

  return <EChart option={option} height={280} ariaLabel="Engagement Rate" />;
}

export function KolDetailView({
  detail,
  isLoading,
  isError,
  onBack,
}: {
  detail: KolDetail | undefined;
  isLoading: boolean;
  isError: boolean;
  onBack: () => void;
}) {
  return (
    <div>
      <Button variant="outline" size="sm" onClick={onBack} className="mb-3 rounded-full">
        ← กลับหน้าหลัก
      </Button>

      {isLoading ? (
        <Card className="p-4 text-sm text-muted-foreground">กำลังโหลด…</Card>
      ) : isError || !detail ? (
        <Card className="p-4">
          <h2 className="text-xl font-bold">ไม่พบ KOL</h2>
        </Card>
      ) : (
        <>
          <Card className="mb-4">
            <CardContent className="p-4">
              <h2 className="text-xl font-bold">{detail.display}</h2>
              <p className="text-sm text-muted-foreground">
                @{detail.username} ·{' '}
                <span style={{ color: TRACKER_GROUP_COLORS[detail.group] ?? '#64748b' }}>
                  {detail.group}
                </span>
              </p>
            </CardContent>
          </Card>

          <div className="mb-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
            <Card>
              <CardContent className="p-3">
                <h3 className="mb-1 text-sm font-semibold">Followers &amp; Views</h3>
                <DetailTrend detail={detail} />
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-3">
                <h3 className="mb-1 text-sm font-semibold">Engagement Rate</h3>
                <DetailEngagement detail={detail} />
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardContent className="p-3">
              <h3 className="mb-2 text-sm font-semibold">โพสต์ล่าสุด</h3>
              {detail.posts.length === 0 ? (
                <p className="text-sm text-muted-foreground">ไม่มีโพสต์ใน 7 วันล่าสุด</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs sm:text-sm">
                    <thead className="text-muted-foreground">
                      <tr className="border-b border-border text-left">
                        <th className="py-2 pr-2 font-normal">โพสต์</th>
                        <th className="px-2 py-2 text-right font-normal">Views</th>
                        <th className="px-2 py-2 text-right font-normal">Likes</th>
                        <th className="px-2 py-2 text-right font-normal">Comments</th>
                        <th className="px-2 py-2 text-right font-normal">Shares</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.posts.map((post) => (
                        <tr key={post.video_id} className="border-b border-border">
                          <td className="py-2 pr-2">
                            <a href={post.url ?? '#'} target="_blank" rel="noopener noreferrer">
                              {(post.posted_at ?? '').slice(0, 10)} {post.is_pinned ? '📌' : ''}
                              {post.is_slideshow ? '🖼️' : '🎬'}
                            </a>
                          </td>
                          <td className="px-2 py-2 text-right font-semibold">
                            {fmtCompact(post.views)}
                          </td>
                          <td className="px-2 py-2 text-right">{fmtCompact(post.likes)}</td>
                          <td className="px-2 py-2 text-right">{fmtCompact(post.comments)}</td>
                          <td className="px-2 py-2 text-right">{fmtCompact(post.shares)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
