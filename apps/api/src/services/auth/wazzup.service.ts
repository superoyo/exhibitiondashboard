import { env } from '../../config/env.js';
import { logger } from '../../config/logger.js';
import { AppError } from '../../utils/AppError.js';

/** Upstream profile payload; shape is the identity backend's, not ours. */
type WazzupProfile = Record<string, unknown>;

/**
 * Wazzup / Fareast Fameline identity.
 *
 * Two upstream operations only:
 *   POST /api/User/Authentication  username+password -> session with access_token
 *   GET  /api/User/Profile         bearer token      -> profile + roles
 *
 * Both are proxied so the browser never talks to the identity backend directly
 * (which would be a CORS problem), and bearer tokens on protected endpoints are
 * validated by calling Get Profile.
 */

const AUTH_PATH = '/api/User/Authentication';
const PROFILE_PATH = '/api/User/Profile';
const UPSTREAM_TIMEOUT_MS = 15_000;

/**
 * Short-lived positive cache. Without it every protected request costs one
 * round-trip to the identity backend; the Python side caches for the same
 * reason. Deliberately short so a revoked token stops working quickly.
 */
const TOKEN_CACHE_TTL_MS = 60_000;
const tokenCache = new Map<string, { expiresAt: number; profile: WazzupProfile }>();

/** Fields the client session needs. Never `password` or `hrPassword`. */
const SESSION_KEYS = [
  'empThaiName',
  'empEngName',
  'nickName',
  'positionName',
  'departmentName',
  'profileURL',
  'email',
  'access_token',
  'expiration',
] as const;

async function upstream(path: string, init: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), UPSTREAM_TIMEOUT_MS);
  try {
    return await fetch(`${env.WAZZUP_BASE_URL}${path}`, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

export async function login(username: string, password: string): Promise<Record<string, unknown>> {
  let response: Response;
  try {
    response = await upstream(AUTH_PATH, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
  } catch (err) {
    logger.warn({ err }, 'Wazzup login unreachable');
    throw new AppError(502, 'เข้าสู่ระบบไม่สำเร็จ กรุณาลองใหม่อีกครั้ง');
  }

  if (response.status === 401 || response.status === 400) {
    throw AppError.unauthorized('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง');
  }
  if (!response.ok) {
    logger.warn({ status: response.status }, 'Wazzup login failed');
    throw new AppError(502, 'เข้าสู่ระบบไม่สำเร็จ กรุณาลองใหม่อีกครั้ง');
  }

  const data = (await response.json()) as Record<string, unknown>;
  if (!data.access_token) throw AppError.unauthorized('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง');

  // Return ONLY the whitelisted keys — never echo the upstream payload, which
  // contains credential fields.
  return Object.fromEntries(SESSION_KEYS.map((k) => [k, data[k] ?? null]));
}

/** The caller's profile, or null when the token is invalid/expired. */
export async function fetchProfile(token: string): Promise<WazzupProfile | null> {
  const cached = tokenCache.get(token);
  if (cached && cached.expiresAt > Date.now()) return cached.profile;

  let response: Response;
  try {
    response = await upstream(PROFILE_PATH, {
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch (err) {
    logger.warn({ err }, 'Wazzup profile unreachable');
    return null;
  }
  if (!response.ok) {
    tokenCache.delete(token);
    return null;
  }

  const profile = (await response.json()) as WazzupProfile;
  tokenCache.set(token, { expiresAt: Date.now() + TOKEN_CACHE_TTL_MS, profile });
  return profile;
}

export async function isTokenValid(token: string): Promise<boolean> {
  if (!token) return false;
  return (await fetchProfile(token)) !== null;
}

/** Drop expired cache entries so a long-lived process does not grow unbounded. */
export function pruneTokenCache(): void {
  const now = Date.now();
  for (const [token, entry] of tokenCache) {
    if (entry.expiresAt <= now) tokenCache.delete(token);
  }
}
