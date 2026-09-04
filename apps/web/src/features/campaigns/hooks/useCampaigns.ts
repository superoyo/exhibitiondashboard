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
 * The home grid pages through EVERY campaign, 15 cards a page — it used to
 * show only the 15 newest, and once the team passed that many reports the
 * older ones simply vanished unless you knew to search (2026-09-02). One
 * query holds the whole list (campaign meta is tiny — name/emoji/counts);
 * paging and search both slice it client-side.
 */
export const HOME_PAGE_SIZE = 15;

export function useAllCampaigns() {
  return useQuery({
    queryKey: queryKeys.campaigns.list(false),
    queryFn: () => listCampaigns(500),
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
