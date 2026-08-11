import { QueryClient } from '@tanstack/react-query';
import { AxiosError } from 'axios';

/**
 * TanStack Query owns every byte of server data.
 *
 * Retry policy matters here: refresh/profile/tie-in endpoints cost real money
 * per Apify call, so a blanket retry would silently multiply the bill. Reads
 * retry once; 4xx never retries.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: (failureCount, error) => {
        const status = error instanceof AxiosError ? error.response?.status : undefined;
        if (status && status >= 400 && status < 500) return false;
        return failureCount < 1;
      },
    },
    mutations: {
      // Mutations here trigger paid scrapes — never retry automatically.
      retry: false,
    },
  },
});

/** Query key factory — one place, so invalidation can never typo a key. */
export const queryKeys = {
  auth: {
    profile: ['auth', 'profile'] as const,
  },
  settings: {
    apifyToken: ['settings', 'apify-token'] as const,
    aiKey: ['settings', 'ai-key'] as const,
    aiStatus: ['settings', 'ai-status'] as const,
  },
  campaigns: {
    all: ['campaigns'] as const,
    list: (includeInactive: boolean) => ['campaigns', 'list', { includeInactive }] as const,
    detail: (key: string) => ['campaigns', 'detail', key] as const,
    summary: ['campaigns', 'summary'] as const,
  },
  kols: {
    directory: ['kols', 'directory'] as const,
  },
  report: {
    data: (campaign: string) => ['report', 'data', campaign] as const,
    refreshStatus: (campaign: string) => ['report', 'refresh-status', campaign] as const,
    profilesStatus: (campaign: string) => ['report', 'profiles-status', campaign] as const,
    tieinStatus: (campaign: string) => ['report', 'tiein-status', campaign] as const,
    comments: (campaign: string) => ['report', 'comments', campaign] as const,
    commentList: (campaign: string, sentiment: string, offset: number) =>
      ['report', 'comment-list', campaign, sentiment, offset] as const,
    commentStatus: (campaign: string) => ['report', 'comment-status', campaign] as const,
  },
} as const;
