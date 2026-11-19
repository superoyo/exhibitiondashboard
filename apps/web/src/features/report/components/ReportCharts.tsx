import { useMemo } from 'react';
import type { ReportRecordDerived } from '@kol/shared';

import { EChart } from '@/components/common/EChart';
import { AXIS_THEME, type EChartsOption } from '@/lib/echarts';
import { fmt } from '@/lib/format';
import type { CategoryColors } from '@/lib/colors';
import { totalsByCategory } from '@/features/report/lib/metrics';

interface ChartProps {
  rows: ReportRecordDerived[];
  colors: CategoryColors;
}

/** Views by category. */
export function CategoryDonut({ rows, colors }: ChartProps) {
  const option = useMemo<EChartsOption>(() => {
    const totals = totalsByCategory(rows);
    return {
      tooltip: { trigger: 'item', valueFormatter: (v) => fmt(v as number) },
      series: [
        {
          type: 'pie',
          radius: ['45%', '72%'],
          label: { color: '#334155' },
          data: colors.categories.map((c) => ({
            name: c,
            value: totals.get(c)?.views ?? 0,
            itemStyle: { color: colors.colorOf(c) },
          })),
        },
      ],
    };
  }, [rows, colors]);

  return <EChart option={option} height={300} ariaLabel="Views ตามหมวด KOL" />;
}

/** Engagement rate per category, derived from category totals (not row means). */
export function CategoryErBar({ rows, colors }: ChartProps) {
  const option = useMemo<EChartsOption>(() => {
    const totals = totalsByCategory(rows);
    return {
      tooltip: { trigger: 'axis', valueFormatter: (v) => `${(v as number).toFixed(2)}%` },
      grid: { left: 50, right: 20, top: 20, bottom: 25 },
      xAxis: { type: 'category', data: colors.categories, ...AXIS_THEME },
      yAxis: {
        type: 'value',
        ...AXIS_THEME,
        axisLabel: { color: '#64748b', formatter: '{value}%' },
      },
      series: [
        {
          type: 'bar',
          barWidth: '45%',
          data: colors.categories.map((c) => {
            const t = totals.get(c);
            const er = t && t.views ? (t.engagement / t.views) * 100 : 0;
            return { value: Number(er.toFixed(2)), itemStyle: { color: colors.colorOf(c) } };
          }),
        },
      ],
    };
  }, [rows, colors]);

  return <EChart option={option} height={300} ariaLabel="Engagement Rate ตามหมวด" />;
}

/** Engagement split by kind, stacked per category. */
export function EngagementStack({ rows, colors }: ChartProps) {
  const option = useMemo<EChartsOption>(() => {
    const totals = totalsByCategory(rows);
    const kinds: Array<
      [key: 'likes' | 'comments' | 'shares' | 'saves', name: string, color: string]
    > = [
      ['likes', 'Likes', '#ef4444'],
      ['comments', 'Comments', '#f59e0b'],
      ['shares', 'Shares', '#3b82f6'],
      ['saves', 'Saves', '#8b5cf6'],
    ];
    return {
      tooltip: { trigger: 'axis', valueFormatter: (v) => fmt(v as number) },
      legend: { bottom: 0, textStyle: { color: '#475569' } },
      grid: { left: 55, right: 20, top: 15, bottom: 45 },
      xAxis: { type: 'category', data: colors.categories, ...AXIS_THEME },
      yAxis: {
        type: 'value',
        ...AXIS_THEME,
        axisLabel: { ...AXIS_THEME.axisLabel, formatter: (v: number) => fmt(v) },
      },
      series: kinds.map(([key, name, color]) => ({
        name,
        type: 'bar',
        stack: 'eng',
        barWidth: '45%',
        data: colors.categories.map((c) => totals.get(c)?.[key] ?? 0),
        itemStyle: { color },
      })),
    };
  }, [rows, colors]);

  return <EChart option={option} height={320} ariaLabel="Engagement แยกชนิดตามหมวด" />;
}

/** Top 10 posts by views. */
export function TopPostsBar({ rows, colors }: ChartProps) {
  const option = useMemo<EChartsOption>(() => {
    // Ascending then take the last 10, so the largest ends up at the top of the
    // bottom-up category axis.
    const top = [...rows].sort((a, b) => a.views - b.views).slice(-10);
    return {
      tooltip: { trigger: 'axis', valueFormatter: (v) => fmt(v as number) },
      grid: { left: 110, right: 30, top: 10, bottom: 25 },
      xAxis: {
        type: 'value',
        ...AXIS_THEME,
        axisLabel: { ...AXIS_THEME.axisLabel, formatter: (v: number) => fmt(v) },
      },
      yAxis: { type: 'category', data: top.map((r) => r.username), ...AXIS_THEME },
      series: [
        {
          type: 'bar',
          data: top.map((r) => ({
            value: r.views,
            itemStyle: { color: colors.colorOf(r.category) },
          })),
        },
      ],
    };
  }, [rows, colors]);

  return <EChart option={option} height={380} ariaLabel="Top 10 โพสต์ ตาม Views" />;
}
