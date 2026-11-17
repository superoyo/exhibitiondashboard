import { useEffect, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { PromoCampaignDetail, PromoInput } from '@kol/shared';

import { queryKeys } from '@/app/queryClient';
import {
  createPromo,
  getPromo,
  listPromos,
  removePromo,
  syncAllPromos,
  syncPromo,
  updatePromo,
} from '@/features/promo/api/promoApi';
import { isStale, STALE_MINUTES } from '@/features/promo/lib/promo';

export function usePromoList() {
  return useQuery({ queryKey: queryKeys.promo.list, queryFn: listPromos });
}

export function usePromoDetail(id: number) {
  return useQuery({
    queryKey: queryKeys.promo.detail(id),
    queryFn: () => getPromo(id),
    enabled: Number.isFinite(id),
  });
}

/** Every write returns the fresh detail, so it goes straight into the cache;
 *  the list is refetched because its totals come from the same snapshot. */
function useStoreDetail() {
  const queryClient = useQueryClient();
  return (detail: PromoCampaignDetail) => {
    queryClient.setQueryData(queryKeys.promo.detail(detail.id), detail);
    void queryClient.invalidateQueries({ queryKey: queryKeys.promo.list });
  };
}

export function useCreatePromo() {
  const store = useStoreDetail();
  return useMutation({ mutationFn: (input: PromoInput) => createPromo(input), onSuccess: store });
}

export function useUpdatePromo() {
  const store = useStoreDetail();
  return useMutation({
    mutationFn: (args: { id: number; input: Partial<PromoInput> }) =>
      updatePromo(args.id, args.input),
    onSuccess: store,
  });
}

export function useRemovePromo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => removePromo(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.promo.all }),
  });
}

export function useSyncPromo() {
  const store = useStoreDetail();
  return useMutation({ mutationFn: (id: number) => syncPromo(id), onSuccess: store });
}

export function useSyncAllPromos() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (staleMinutes?: number) => syncAllPromos(staleMinutes),
    onSuccess: (result) => {
      queryClient.setQueryData(queryKeys.promo.list, result.campaigns);
      // Open detail pages hold the older snapshot.
      void queryClient.invalidateQueries({ queryKey: ['promo', 'detail'] });
    },
  });
}

/**
 * The team edits their sheets all day and nobody thinks to press "update"
 * before reading a number, so opening the overview re-reads any deal whose
 * snapshot is older than STALE_MINUTES — once per page open. Reading a sheet
 * costs nothing (no Apify), which is what makes doing it unasked acceptable.
 */
export function useAutoSyncAll(ready: boolean) {
  const sync = useSyncAllPromos();
  const started = useRef(false);
  const run = sync.mutate;
  useEffect(() => {
    if (!ready || started.current) return;
    started.current = true;
    run(STALE_MINUTES);
  }, [ready, run]);
  return sync.isPending;
}

/** Same idea for one deal opened directly (a bookmark, a shared link). */
export function useAutoSyncOne(detail: PromoCampaignDetail | undefined) {
  const sync = useSyncPromo();
  const started = useRef(false);
  const run = sync.mutate;
  const id = detail?.id;
  const stale = detail ? isStale(detail.synced_at) : false;
  useEffect(() => {
    if (id === undefined || started.current) return;
    started.current = true;
    if (stale) run(id);
  }, [id, stale, run]);
  return sync.isPending;
}
