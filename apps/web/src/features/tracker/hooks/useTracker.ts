import { useQuery } from '@tanstack/react-query';

import { getHealth, getKolDetail, getSummary, getTrend } from '@/features/tracker/api/trackerApi';

export const trackerKeys = {
  health: ['tracker', 'health'] as const,
  summary: (date: string, group: string) => ['tracker', 'summary', date, group] as const,
  trend: (metric: string, group: string, days: number) =>
    ['tracker', 'trend', metric, group, days] as const,
  detail: (username: string) => ['tracker', 'kol', username] as const,
};

export function useHealth() {
  return useQuery({ queryKey: trackerKeys.health, queryFn: getHealth });
}

export function useSummary(date: string, group: string) {
  return useQuery({
    queryKey: trackerKeys.summary(date, group),
    queryFn: () => getSummary(date, group),
    // Keep the previous page of data visible while switching group/date, so the
    // KPI row and charts don't flash empty on every filter change.
    placeholderData: (prev) => prev,
  });
}

export function useTrend(metric: string, group: string, days = 30) {
  return useQuery({
    queryKey: trackerKeys.trend(metric, group, days),
    queryFn: () => getTrend(metric, group, days),
    placeholderData: (prev) => prev,
  });
}

export function useKolDetail(username: string | null) {
  return useQuery({
    queryKey: trackerKeys.detail(username ?? ''),
    queryFn: () => getKolDetail(username as string),
    enabled: Boolean(username),
  });
}
