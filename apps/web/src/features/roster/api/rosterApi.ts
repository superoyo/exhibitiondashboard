import type {
  BulkRosterInput,
  BulkRosterResponse,
  GroupKpiResponse,
  KolKpi,
  ResolveHandlesResponse,
  RosterAddInput,
  RosterDeleteResponse,
  RosterKind,
  RosterKol,
  RosterListResponse,
  RosterPatchInput,
} from '@kol/shared';

import { api } from '@/lib/axios';

/**
 * Report rosters are scoped by ?campaign=; the tracker roster is global and must
 * NOT receive the param (the backend would default it to 'pao' and filter a
 * table that has no campaign column).
 */
function scope(kind: RosterKind, campaign: string) {
  return kind === 'report' ? { campaign } : undefined;
}

export async function listRoster(kind: RosterKind, campaign: string): Promise<RosterKol[]> {
  const { data } = await api.get<RosterListResponse>(`/roster/${kind}`, {
    params: scope(kind, campaign),
  });
  return data.kols;
}

/** Group-total KPIs ("7M Imp across Micro Package"). Report rosters only. */
export async function getGroupKpis(campaign: string): Promise<Record<string, KolKpi[]>> {
  const { data } = await api.get<GroupKpiResponse>('/roster/report/groupkpi', {
    params: { campaign },
  });
  return data.groups;
}

export async function saveGroupKpi(campaign: string, group: string, kpis: KolKpi[]): Promise<void> {
  await api.post('/roster/report/groupkpi', { group, kpis }, { params: { campaign } });
}

export async function addRosterKol(
  kind: RosterKind,
  campaign: string,
  input: RosterAddInput,
): Promise<RosterKol> {
  const { data } = await api.post<RosterKol>(`/roster/${kind}`, input, {
    params: scope(kind, campaign),
  });
  return data;
}

export async function patchRosterKol(
  kind: RosterKind,
  id: number,
  input: RosterPatchInput,
): Promise<RosterKol> {
  const { data } = await api.patch<RosterKol>(`/roster/${kind}/${id}`, input);
  return data;
}

export async function deleteRosterKol(kind: RosterKind, id: number): Promise<RosterDeleteResponse> {
  const { data } = await api.delete<RosterDeleteResponse>(`/roster/${kind}/${id}`);
  return data;
}

/** REPLACES the campaign's entire roster. Never appends. */
export async function bulkReplaceRoster(
  campaign: string,
  input: BulkRosterInput,
): Promise<BulkRosterResponse> {
  const { data } = await api.post<BulkRosterResponse>('/roster/report/bulk', input, {
    params: { campaign },
  });
  return data;
}

/** The online file this campaign was last imported from, or '' if none. */
export async function getSheetLink(campaign: string): Promise<string> {
  const { data } = await api.get<{ url: string }>('/roster/report/sheet', {
    params: { campaign },
  });
  return data.url;
}

/** Fetch a spreadsheet through the backend proxy (client-side fetch is CORS-blocked). */
export async function fetchSheetBytes(url: string): Promise<ArrayBuffer> {
  const { data } = await api.get<ArrayBuffer>('/sheet/fetch', {
    params: { url },
    responseType: 'arraybuffer',
  });
  return data;
}

/** Resolve post URLs to their posting handle and canonical final URL. */
export async function resolveHandles(urls: string[]): Promise<ResolveHandlesResponse> {
  const { data } = await api.post<ResolveHandlesResponse>('/resolve-handles', { urls });
  return data;
}
