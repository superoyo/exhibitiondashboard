import type {
  Campaign,
  CampaignArchiveResponse,
  CampaignCreateInput,
  CampaignListResponse,
  CampaignPatchInput,
  CampaignRenameResponse,
  ViewTokenResponse,
} from '@kol/shared';

import { api } from '@/lib/axios';

export async function listCampaigns(limit: number, includeInactive = false): Promise<Campaign[]> {
  const { data } = await api.get<CampaignListResponse>('/campaigns', {
    params: { limit, ...(includeInactive ? { include_inactive: true } : {}) },
  });
  return data.campaigns;
}

export async function getCampaign(key: string): Promise<Campaign> {
  const { data } = await api.get<Campaign>(`/campaigns/${encodeURIComponent(key)}`);
  return data;
}

export async function createCampaign(input: CampaignCreateInput): Promise<Campaign> {
  const { data } = await api.post<Campaign>('/campaigns', input);
  return data;
}

export async function patchCampaign(key: string, input: CampaignPatchInput): Promise<Campaign> {
  const { data } = await api.patch<Campaign>(`/campaigns/${encodeURIComponent(key)}`, input);
  return data;
}

/**
 * Soft delete — the backend archives (active=false) rather than dropping rows,
 * so KOL data survives and the URL keeps resolving.
 */
export async function archiveCampaign(key: string): Promise<CampaignArchiveResponse> {
  const { data } = await api.delete<CampaignArchiveResponse>(
    `/campaigns/${encodeURIComponent(key)}`,
  );
  return data;
}

/** Changes the URL key across campaigns, roster, posts and settings. */
export async function renameCampaign(key: string, newKey: string): Promise<CampaignRenameResponse> {
  const { data } = await api.post<CampaignRenameResponse>(
    `/campaigns/${encodeURIComponent(key)}/rename`,
    { new_key: newKey },
  );
  return data;
}

export async function getViewToken(key: string): Promise<ViewTokenResponse> {
  const { data } = await api.get<ViewTokenResponse>(
    `/campaigns/${encodeURIComponent(key)}/view-token`,
  );
  return data;
}
