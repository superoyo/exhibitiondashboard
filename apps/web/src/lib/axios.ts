import axios, { AxiosError, type AxiosInstance } from 'axios';

import { env } from '@/config/env';
import { isPublicPath, routes } from '@/config/routes';
import { clearSession, getAccessToken } from '@/features/auth/lib/session';

/**
 * The one HTTP client. Replaces the legacy `window.fetch` monkey-patch in
 * auth.js — with the same two behaviours, which are easy to lose:
 *
 *  1. Attach `Authorization: Bearer <token>` to every /api/ call EXCEPT
 *     /api/auth/* (those either carry their own header or must go out clean).
 *  2. On 401 from a non-auth call, drop the session and bounce to /login with
 *     `?next=` so the user lands back where they were.
 *
 * Anything that talks to the API must go through this instance. A stray
 * `fetch()` silently loses its auth header — that includes blob downloads
 * (PPTX / CSV), which is exactly where it is easiest to forget.
 */
export const api: AxiosInstance = axios.create({
  baseURL: `${env.apiBaseUrl}/api`,
  headers: { 'Content-Type': 'application/json' },
});

/** /auth/* is exempt: login has no token yet, profile supplies its own. */
function isAuthCall(url: string | undefined): boolean {
  return (url ?? '').includes('/auth/');
}

api.interceptors.request.use((config) => {
  if (!isAuthCall(config.url)) {
    const token = getAccessToken();
    if (token) config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    const status = error.response?.status;
    const url = error.config?.url;

    // Public report pages read open endpoints with no session at all — a 401
    // there must surface as an error, never as a redirect to /login, or every
    // client link turns into a login wall.
    if (
      status === 401 &&
      !isAuthCall(url) &&
      !isPublicPath(window.location.pathname, window.location.search)
    ) {
      clearSession();
      const next = encodeURIComponent(window.location.pathname + window.location.search);
      window.location.replace(`${routes.login}?next=${next}`);
    }
    return Promise.reject(error);
  },
);

/**
 * Pull the human-readable message out of a FastAPI/Express error body.
 * Both shapes use `detail`; falls back to the Axios message.
 */
export function apiErrorMessage(error: unknown, fallback = 'เกิดข้อผิดพลาด กรุณาลองใหม่'): string {
  if (error instanceof AxiosError) {
    const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
    if (error.code === 'ERR_NETWORK') return 'เชื่อมต่อไม่ได้ กรุณาลองใหม่อีกครั้ง';
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}
