import type { LoginResponse, Session, WazzupProfile } from '@kol/shared';

/**
 * Session persistence.
 *
 * `wz_session` in localStorage is the single source of truth for the bearer
 * token: the Axios interceptor reads it directly rather than through Redux, so
 * a request fired outside React (or before the store hydrates) can never go
 * out unauthenticated.
 *
 * The key name and field names are load-bearing — live browsers already hold
 * sessions under this key, and a sibling app hands us tokens in this shape.
 */
export const SESSION_KEY = 'wz_session';

/** Photos are inlined as data: URIs; anything larger blows out localStorage. */
const MAX_PHOTO_BYTES = 400_000;

export function readSession(): Session | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const s = JSON.parse(raw) as Partial<Session> | null;
    if (!s?.access_token) return null;
    // An absent expiration is valid (SSO handoff sends none) — in that case the
    // first 401 from the API is what bounces the user to /login.
    if (s.expiration && new Date(s.expiration) <= new Date()) {
      localStorage.removeItem(SESSION_KEY);
      return null;
    }
    return s as Session;
  } catch {
    return null;
  }
}

export function writeSession(session: Session): void {
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

export function clearSession(): void {
  localStorage.removeItem(SESSION_KEY);
}

export function getAccessToken(): string | null {
  return readSession()?.access_token ?? null;
}

/** Build the photo data: URI / URL from a profile payload, if usable. */
function photoFrom(profile: WazzupProfile): string | undefined {
  if (profile.wazzupPhotoBase64) {
    let type = (profile.wazzupPhotoFileType ?? 'jpeg').replace(/^\./, '').toLowerCase();
    if (!type.includes('/')) type = `image/${type === 'jpg' ? 'jpeg' : type}`;
    const uri = `data:${type};base64,${profile.wazzupPhotoBase64}`;
    if (uri.length < MAX_PHOTO_BYTES) return uri;
  }
  if (profile.profileURL && /^https?:/i.test(profile.profileURL)) return profile.profileURL;
  return undefined;
}

/** Merge a login response with the richer profile payload into one session. */
export function buildSession(login: LoginResponse, profile?: WazzupProfile): Session {
  const p = profile ?? {};
  const displayName = p.empThaiName ?? p.empEngName ?? login.empThaiName ?? login.empEngName ?? '';

  const session: Session = {
    access_token: login.access_token ?? '',
    expiration: login.expiration ?? null,
    displayName,
    empThaiName: p.empThaiName ?? login.empThaiName ?? '',
    empEngName: p.empEngName ?? login.empEngName ?? '',
    nickName: p.nickName ?? login.nickName ?? '',
    email: p.email ?? login.email ?? '',
    positionName: p.positionName ?? login.positionName ?? '',
    departmentName: p.departmentName ?? login.departmentName ?? '',
  };

  const photo =
    photoFrom(p) ??
    (login.profileURL && /^https?:/i.test(login.profileURL) ? login.profileURL : undefined);
  if (photo) session.photo = photo;

  return session;
}

/** Session built from an SSO handoff: token is valid, but no expiry was sent. */
export function sessionFromProfile(token: string, profile: WazzupProfile): Session {
  return buildSession(
    {
      empThaiName: null,
      empEngName: null,
      nickName: null,
      positionName: null,
      departmentName: null,
      profileURL: null,
      email: null,
      access_token: token,
      expiration: null,
    },
    profile,
  );
}

/**
 * Same-origin redirect target after login. Rejects protocol-relative `//host`
 * so `?next=` can never be used as an open redirect.
 */
export function safeNextUrl(search: string): string {
  const next = new URLSearchParams(search).get('next') ?? '/';
  return next.startsWith('/') && !next.startsWith('//') ? next : '/';
}
