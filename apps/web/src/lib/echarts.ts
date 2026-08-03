import type { EChartsOption } from 'echarts';

/**
 * Shared ECharts styling, carried over from the axis/grid theme the legacy
 * pages repeated inline in every `setOption` call.
 */
export const AXIS_THEME = {
  axisLine: { lineStyle: { color: '#cbd5e1' } },
  axisLabel: { color: '#64748b' },
  splitLine: { lineStyle: { color: '#eef2f7' } },
} as const;

/** Build a vertical gradient fill for a line series' area. */
export function areaGradient(color: string) {
  return {
    type: 'linear' as const,
    x: 0,
    y: 0,
    x2: 0,
    y2: 1,
    colorStops: [
      { offset: 0, color: `${color}55` },
      { offset: 1, color: `${color}05` },
    ],
  };
}

/** Trend line colour per metric, matching the legacy Tracker. */
export const TREND_COLORS: Record<string, string> = {
  views: '#2563eb',
  engagement: '#059669',
  followers: '#d97706',
};

export type { EChartsOption };
