import type { AiStatus, SecretInfo, SecretSaveResult, TokenTestResult } from '@kol/shared';

import { api } from '@/lib/axios';

// ---- Apify token ----------------------------------------------------------

export async function getApifyToken(): Promise<SecretInfo> {
  const { data } = await api.get<SecretInfo>('/token');
  return data;
}

export async function saveApifyToken(token: string): Promise<SecretSaveResult> {
  const { data } = await api.post<SecretSaveResult>('/token', { token });
  return data;
}

/** Live credential check against Apify — does not change the stored token. */
export async function testApifyToken(): Promise<TokenTestResult> {
  const { data } = await api.post<TokenTestResult>('/token/test');
  return data;
}

// ---- Claude API key -------------------------------------------------------

export async function getAiKey(): Promise<SecretInfo> {
  const { data } = await api.get<SecretInfo>('/ai/key');
  return data;
}

/** The backend live-checks the new key and returns the result in `check`. */
export async function saveAiKey(token: string): Promise<SecretSaveResult> {
  const { data } = await api.post<SecretSaveResult>('/ai/key', { token });
  return data;
}

export async function getAiStatus(force = false): Promise<AiStatus> {
  const { data } = await api.get<AiStatus>('/ai/status', {
    params: force ? { force: 1 } : undefined,
  });
  return data;
}
