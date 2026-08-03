import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { CampaignCreateInput, CampaignPatchInput } from '@kol/shared';

import { queryKeys } from '@/app/queryClient';
import {
  archiveCampaign,
  createCampaign,
  listCampaigns,
  patchCampaign,
  renameCampaign,
} from '@/features/campaigns/api/campaignsApi';

/**
 * The home grid shows the 15 newest campaigns. Search needs the full set, so it
 * is a SECOND query that only runs once the user actually types — the legacy
 * page did the same thing with a lazily-filled `SEARCH_CACHE`.
 */
export const HOME_LIMIT = 15;
export const SEARCH_LIMIT = 100;

export function useLatestCampaigns() {
  return useQuery({
    queryKey: queryKeys.campaigns.list(false),
    queryFn: () => listCampaigns(HOME_LIMIT),
  });
}

export function useSearchableCampaigns(enabled: boolean) {
  return useQuery({
    queryKey: ['campaigns', 'list', 'searchable'] as const,
    queryFn: () => listCampaigns(SEARCH_LIMIT),
    enabled,
  });
}

/** Invalidate every campaign list after a create/edit/archive. */
function useInvalidateCampaigns() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: queryKeys.campaigns.all });
}

export function useCreateCampaign() {
  const invalidate = useInvalidateCampaigns();
  return useMutation({
    mutationFn: (input: CampaignCreateInput) => createCampaign(input),
    onSuccess: invalidate,
  });
}

export function useArchiveCampaign() {
  const invalidate = useInvalidateCampaigns();
  return useMutation({
    mutationFn: (key: string) => archiveCampaign(key),
    onSuccess: invalidate,
  });
}

/**
 * Edit is two calls in a fixed order: rename the key FIRST (if it changed),
 * then PATCH the rest against whichever key won. Doing it the other way round
 * would patch a key that no longer exists.
 */
export function useUpdateCampaign() {
  const invalidate = useInvalidateCampaigns();
  return useMutation({
    mutationFn: async (args: { key: string; newKey?: string; patch: CampaignPatchInput }) => {
      let targetKey = args.key;
      if (args.newKey && args.newKey !== args.key) {
        const renamed = await renameCampaign(args.key, args.newKey);
        targetKey = renamed.key;
      }
      return patchCampaign(targetKey, args.patch);
    },
    onSuccess: invalidate,
  });
}
