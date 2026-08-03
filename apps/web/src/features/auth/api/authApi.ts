import type { LoginInput, LoginResponse, ProfileResponse } from '@kol/shared';

import { api } from '@/lib/axios';

/** POST /api/auth/login — server-side proxy of the Wazzup login (dodges CORS). */
export async function login(input: LoginInput): Promise<LoginResponse> {
  const { data } = await api.post<LoginResponse>('/auth/login', input);
  return data;
}

/**
 * GET /api/auth/profile — richer profile (full Thai name + employee photo).
 * Takes an explicit token because it is also used to validate a token that is
 * not yet the stored session (the SSO handoff).
 */
export async function fetchProfile(token: string): Promise<ProfileResponse> {
  const { data } = await api.get<ProfileResponse>('/auth/profile', {
    headers: { Authorization: `Bearer ${token}` },
  });
  return data;
}
