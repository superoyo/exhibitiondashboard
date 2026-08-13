import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { queryKeys } from '@/app/queryClient';
import {
  getActiveJobs,
  getCommentList,
  getCommentStatus,
  getComments,
  getPackshot,
  getRefreshStatus,
  getReportData,
  getTieinStatus,
  getViewCommentList,
  getViewComments,
  resetCost,
  savePackshot,
} from '@/features/report/api/reportApi';

/** Poll intervals, unchanged from the legacy page. */
const REFRESH_POLL_MS = 3000;
const TIEIN_POLL_MS = 4000;
const COMMENT_POLL_MS = 4000;

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

/**
 * Stored comment breakdown. Cheap: it reads rows the scrape already wrote, so
 * it is safe to load with the page. The scrape itself is a separate, explicit
 * action — see useCommentStatus.
 */
export function useComments(campaign: string, enabled: boolean, viewToken = '') {
  return useQuery({
    queryKey: queryKeys.report.comments(campaign),
    // With a view token there is no session, so the read goes through the
    // token-addressed endpoint instead. Same payload either way, hence the same
    // cache key.
    queryFn: () => (viewToken ? getViewComments(viewToken) : getComments(campaign)),
    enabled: enabled && Boolean(campaign),
  });
}

/** Comment scrape progress. Polls only while a job is actually running. */
export function useCommentStatus(campaign: string, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.report.commentStatus(campaign),
    queryFn: () => getCommentStatus(campaign),
    enabled: enabled && Boolean(campaign),
    refetchInterval: (query) => (query.state.data?.status === 'running' ? COMMENT_POLL_MS : false),
  });
}

/**
 * One page of product comments. Keyed on the filter and offset so switching
 * back to a page already seen is instant, and `placeholderData` keeps the
 * previous page on screen while the next one loads instead of flashing empty.
 */
export function useCommentList(
  campaign: string,
  category: string,
  offset: number,
  limit: number,
  enabled: boolean,
  viewToken = '',
) {
  return useQuery({
    queryKey: queryKeys.report.commentList(campaign, category, offset),
    queryFn: () =>
      viewToken
        ? getViewCommentList(viewToken, category, offset, limit)
        : getCommentList(campaign, category, offset, limit),
    enabled: enabled && Boolean(campaign),
    placeholderData: (prev) => prev,
  });
}

/**
 * Every background job, for the status dock. Polls faster while something is
 * running and slower when idle — the endpoint only reads memory, but there is
 * no reason to ask every few seconds when the answer is "nothing".
 */
export function useActiveJobs() {
  return useQuery({
    queryKey: queryKeys.jobs.active(),
    queryFn: getActiveJobs,
    refetchInterval: (query) => ((query.state.data?.length ?? 0) > 0 ? 3000 : 10000),
  });
}
