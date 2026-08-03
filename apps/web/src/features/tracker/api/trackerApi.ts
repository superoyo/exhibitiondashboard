import type { HealthResponse, KolDetail, SummaryResponse, TrendResponse } from '@kol/shared';

import { api } from '@/lib/axios';

export async function getHealth(): Promise<HealthResponse> {
  const { data } = await api.get<HealthResponse>('/health');
  return data;
}

export async function getSummary(date: string, group: string): Promise<SummaryResponse> {
  const { data } = await api.get<SummaryResponse>('/summary', { params: { date, group } });
  return data;
}

export async function getTrend(metric: string, group: string, days = 30): Promise<TrendResponse> {
  const { data } = await api.get<TrendResponse>('/trend', { params: { metric, group, days } });
  return data;
}

export async function getKolDetail(username: string): Promise<KolDetail> {
  const { data } = await api.get<KolDetail>(`/kols/${encodeURIComponent(username)}`);
  return data;
}
