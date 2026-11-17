import type {
  PromoCampaignDetail,
  PromoCampaignSummary,
  PromoInput,
  PromoListResponse,
  PromoSyncAllResponse,
} from '@kol/shared';

import { api } from '@/lib/axios';

export async function listPromos(): Promise<PromoCampaignSummary[]> {
  const { data } = await api.get<PromoListResponse>('/promo/campaigns');
  return data.campaigns;
}

export async function getPromo(id: number): Promise<PromoCampaignDetail> {
  const { data } = await api.get<PromoCampaignDetail>(`/promo/campaigns/${id}`);
  return data;
}

/** Registers the deal AND reads its sheet; a sheet that cannot be read still
 *  creates the deal, with `sync_error` saying why. */
export async function createPromo(input: PromoInput): Promise<PromoCampaignDetail> {
  const { data } = await api.post<PromoCampaignDetail>('/promo/campaigns', input);
  return data;
}

export async function updatePromo(
  id: number,
  input: Partial<PromoInput>,
): Promise<PromoCampaignDetail> {
  const { data } = await api.patch<PromoCampaignDetail>(`/promo/campaigns/${id}`, input);
  return data;
}

/** Hides the deal from this page. The team's sheet is never touched. */
export async function removePromo(id: number): Promise<void> {
  await api.delete(`/promo/campaigns/${id}`);
}

export async function syncPromo(id: number): Promise<PromoCampaignDetail> {
  const { data } = await api.post<PromoCampaignDetail>(`/promo/campaigns/${id}/sync`);
  return data;
}

/** `staleMinutes` limits the re-read to deals not read that recently. */
export async function syncAllPromos(staleMinutes?: number): Promise<PromoSyncAllResponse> {
  const { data } = await api.post<PromoSyncAllResponse>(
    '/promo/sync',
    staleMinutes === undefined ? {} : { stale_minutes: staleMinutes },
  );
  return data;
}
