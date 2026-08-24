import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { RosterAddInput, RosterKind, RosterPatchInput } from '@kol/shared';

import {
  addRosterKol,
  deleteRosterKol,
  getSheetLink,
  listRoster,
  patchRosterKol,
} from '@/features/roster/api/rosterApi';

/** Query keys are scoped by kind AND campaign — the two rosters are distinct. */
export const rosterKeys = {
  list: (kind: RosterKind, campaign: string) => ['roster', kind, campaign] as const,
  sheet: (campaign: string) => ['roster', 'sheet', campaign] as const,
};

export function useRoster(kind: RosterKind, campaign: string, enabled = true) {
  return useQuery({
    queryKey: rosterKeys.list(kind, campaign),
    queryFn: () => listRoster(kind, campaign),
    // Off on sessionless pages: the endpoint requires auth and would 401.
    enabled,
  });
}

/** Linked online file for re-sync. Report rosters only. */
export function useSheetLink(campaign: string, enabled: boolean) {
  return useQuery({
    queryKey: rosterKeys.sheet(campaign),
    queryFn: () => getSheetLink(campaign),
    enabled,
  });
}

function useInvalidateRoster(kind: RosterKind, campaign: string) {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: rosterKeys.list(kind, campaign) });
}

export function useAddRosterKol(kind: RosterKind, campaign: string) {
  const invalidate = useInvalidateRoster(kind, campaign);
  return useMutation({
    mutationFn: (input: RosterAddInput) => addRosterKol(kind, campaign, input),
    onSuccess: invalidate,
  });
}

export function usePatchRosterKol(kind: RosterKind, campaign: string) {
  const invalidate = useInvalidateRoster(kind, campaign);
  return useMutation({
    mutationFn: (args: { id: number; input: RosterPatchInput }) =>
      patchRosterKol(kind, args.id, args.input),
    onSuccess: invalidate,
  });
}

export function useDeleteRosterKol(kind: RosterKind, campaign: string) {
  const invalidate = useInvalidateRoster(kind, campaign);
  return useMutation({
    mutationFn: (id: number) => deleteRosterKol(kind, id),
    onSuccess: invalidate,
  });
}
