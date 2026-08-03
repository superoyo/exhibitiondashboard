/**
 * Wazzup / Fareast Fameline identity.
 *
 * The backend proxies both upstream calls (POST /auth/login, GET /auth/profile)
 * to dodge browser CORS, and strips everything the client must never see —
 * notably `password` and `hrPassword`.
 */

/** Exact key set returned by `POST /api/auth/login` (see app/api/routes.py:53). */
export interface LoginResponse {
  empThaiName: string | null;
  empEngName: string | null;
  nickName: string | null;
  positionName: string | null;
  departmentName: string | null;
  profileURL: string | null;
  email: string | null;
  access_token: string | null;
  expiration: string | null;
}

/** Profile fields the UI reads out of `GET /api/auth/profile` -> `.profile`. */
export interface WazzupProfile {
  empThaiName?: string | null;
  empEngName?: string | null;
  nickName?: string | null;
  positionName?: string | null;
  departmentName?: string | null;
  email?: string | null;
  profileURL?: string | null;
  wazzupPhotoBase64?: string | null;
  wazzupPhotoFileType?: string | null;
}

export interface ProfileResponse {
  profile?: WazzupProfile;
}

/**
 * What we persist in `localStorage.wz_session`.
 *
 * The key name and shape are load-bearing: another app hands us a token via
 * `#token=` and existing browsers already hold sessions under this key, so
 * renaming it would silently sign everyone out.
 */
export interface Session {
  access_token: string;
  /** ISO string, or null when the token came from an SSO handoff (no exp sent). */
  expiration: string | null;
  displayName: string;
  empThaiName: string;
  empEngName: string;
  nickName: string;
  email: string;
  positionName: string;
  departmentName: string;
  /** data: URI (kept under 400 KB) or an https: URL. */
  photo?: string;
}
