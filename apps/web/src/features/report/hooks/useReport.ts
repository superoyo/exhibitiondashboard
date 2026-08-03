import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { queryKeys } from '@/app/queryClient';
import {
  getPackshot,
  getRefreshStatus,
  getReportData,
  getTieinStatus,
  resetCost,
  savePackshot,
} from '@/features/report/api/reportApi';

/** Poll intervals, unchanged from the legacy page. */
const REFRESH_POLL_MS = 3000;
const TIEIN_POLL_MS = 4000;

export function useReportData(campaign: string) {
  return useQuery({
    queryKey: queryKeys.report.data(campaign),
    queryFn: () => getReportData(campaign),
    enabled: Boolean(campaign),
  });
}

/**
 * Refresh progress. Polls only while a job is actually running — these
 * endpoints are cheap, but the job they report on spends Apify credits, so the
 * UI must never trigger one implicitly.
 */
export function useRefreshStatus(campaign: string, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.report.refreshStatus(campaign),
    queryFn: () => getRefreshStatus(campaign),
    enabled: enabled && Boolean(campaign),
    refetchInterval: (query) => (query.state.data?.status === 'running' ? REFRESH_POLL_MS : false),
  });
}

export function useTieinStatus(campaign: string, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.report.tieinStatus(campaign),
    queryFn: () => getTieinStatus(campaign),
    enabled: enabled && Boolean(campaign),
    refetchInterval: (query) => (query.state.data?.status === 'running' ? TIEIN_POLL_MS : false),
  });
}

export function usePackshot(campaign: string, enabled: boolean) {
  return useQuery({
    queryKey: ['report', 'packshot', campaign] as const,
    queryFn: () => getPackshot(campaign),
    enabled: enabled && Boolean(campaign),
  });
}

export function useSavePackshot(campaign: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (imageBase64: string) => savePackshot(campaign, imageBase64),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['report', 'packshot', campaign] }),
  });
}

export function useResetCost(campaign: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => resetCost(campaign),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.report.data(campaign) }),
  });
}
