import { useMemo } from 'react';
import {
  TRACKER_GROUP_COLORS,
  type TrackerKol,
  type TrendMetric,
  type TrendPoint,
} from '@kol/shared';

import { EChart } from '@/components/common/EChart';
import { areaGradient, AXIS_THEME, TREND_COLORS, type EChartsOption } from '@/lib/echarts';
import { fmtCompact } from '@/lib/format';

const GROUP_FALLBACK = '#64748b';

function groupColor(group: string): string {
  return TRACKER_GROUP_COLORS[group] ?? GROUP_FALLBACK;
}

/** Daily trend of one metric across the filtered group. */
export function TrendChart({ series, metric }: { series: TrendPoint[]; metric: TrendMetric }) {
  const option = useMemo<EChartsOption>(() => {
    const color = TREND_COLORS[metric] ?? TREND_COLORS.views ?? '#2563eb';
    return {
      grid: { left: 55, right: 20, top: 15, bottom: 25 },
      tooltip: { trigger: 'axis', valueFormatter: (v) => fmtCompact(v as number) },
      xAxis: { type: 'category', data: series.map((p) => p.date), ...AXIS_THEME },
      yAxis: {
        type: 'value',
        ...AXIS_THEME,
        // The legacy chart left these as raw grouped numbers, which clipped to
        // ",000,000" once totals reached 7 digits — the label was wider than the
        // 55px grid margin. Compact notation matches this chart's own tooltip.
        axisLabel: { ...AXIS_THEME.axisLabel, formatter: (v: number) => fmtCompact(v) },
      },
      series: [
        {
          type: 'line',
          smooth: true,
          // Symbols only on short series; on 30 points they become noise.
          showSymbol: series.length < 15,
          data: series.map((p) => p.value),
          lineStyle: { color, width: 2 },
          itemStyle: { color },
          areaStyle: { color: areaGradient(color) },
        },
      ],
    };
  }, [series, metric]);

  return <EChart option={option} height={260} ariaLabel="แนวโน้มรายวัน" />;
}

/** Share of views by group. */
export function GroupDonut({ kols }: { kols: TrackerKol[] }) {
  const option = useMemo<EChartsOption>(() => {
    const byGroup = new Map<string, number>();
    for (const k of kols) byGroup.set(k.group, (byGroup.get(k.group) ?? 0) + k.views_7d);
    return {
      tooltip: {
        trigger: 'item',
        formatter: (p) => {
          const point = p as { name: string; value: number; percent?: number };
          return `${point.name}<br>${fmtCompact(point.value)} (${point.percent ?? 0}%)`;
        },
      },
      series: [
        {
          type: 'pie',
          radius: ['45%', '72%'],
          label: { color: '#334155', fontSize: 11 },
          data: [...byGroup].map(([group, value]) => ({
            name: group,
            value,
            itemStyle: { color: groupColor(group) },
          })),
        },
      ],
    };
  }, [kols]);

  return <EChart option={option} height={260} ariaLabel="สัดส่วน Views ตามกลุ่ม" />;
}

/** Top 10 KOLs by views, as a horizontal bar chart. */
export function TopKolBar({ kols }: { kols: TrackerKol[] }) {
  const option = useMemo<EChartsOption>(() => {
    // Reversed because ECharts draws the category axis bottom-up.
    const top = [...kols]
      .sort((a, b) => b.views_7d - a.views_7d)
      .slice(0, 10)
      .reverse();
    return {
      grid: { left: 90, right: 20, top: 10, bottom: 20 },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        valueFormatter: (v) => fmtCompact(v as number),
      },
      xAxis: { type: 'value', ...AXIS_THEME },
      yAxis: {
        type: 'category',
        data: top.map((k) => k.display),
        ...AXIS_THEME,
        axisLabel: { color: '#8b97a8', width: 80, overflow: 'truncate' },
      },
      series: [
        {
          type: 'bar',
          data: top.map((k) => ({
            value: k.views_7d,
            itemStyle: { color: groupColor(k.group), borderRadius: [0, 4, 4, 0] },
          })),
        },
      ],
    };
  }, [kols]);

  return <EChart option={option} height={300} ariaLabel="Top 10 KOL by Views" />;
}

/** Followers vs views on log/log axes. */
export function FollowersScatter({ kols }: { kols: TrackerKol[] }) {
  const option = useMemo<EChartsOption>(() => {
    const data = kols
      // A log axis cannot plot zero, and a KOL with no followers carries no
      // signal here anyway.
      .filter((k) => k.followers > 0)
      .map((k) => ({
        value: [k.followers, Math.max(k.views_7d, 1)],
        name: k.display,
        itemStyle: { color: groupColor(k.group) },
      }));
    return {
      grid: { left: 55, right: 20, top: 10, bottom: 40 },
      tooltip: {
        // A scatter tooltip is always a single point, but the callback is typed
        // for the shared (single | array) case — narrow through `unknown`.
        formatter: (p) => {
          const point = p as unknown as { data: { name: string }; value: [number, number] };
          return `${point.data.name}<br>Followers: ${fmtCompact(point.value[0])}<br>Views: ${fmtCompact(point.value[1])}`;
        },
      },
      xAxis: { type: 'log', name: 'Followers', nameLocation: 'middle', nameGap: 25, ...AXIS_THEME },
      yAxis: { type: 'log', name: 'Views', ...AXIS_THEME },
      series: [{ type: 'scatter', symbolSize: 9, data }],
    };
  }, [kols]);

  return <EChart option={option} height={300} ariaLabel="Followers vs Views" />;
}
