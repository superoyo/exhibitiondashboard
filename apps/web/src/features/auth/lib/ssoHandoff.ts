import { fetchProfile } from '@/features/auth/api/authApi';
import { readSession, sessionFromProfile, writeSession } from './session';

import type { Session } from '@kol/shared';

/**
 * SSO handoff: a sibling app that already holds a Wazzup session can link here
 * with `#token=<access_token>` (or `?token=`). We validate the token against
 * /api/auth/profile, promote it to a real session, and scrub it off the URL.
 *
 * The token is stripped whether or not validation succeeded, so a stale token
 * never lingers in the address bar (or in a copy-pasted link) being retried.
 *
 * Runs once, before the first render — the legacy code achieved the same
 * ordering by wrapping `window.fetch` before its first `await`.
 */
export async function resolveSession(): Promise<Session | null> {
  const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, ''));
  const queryParams = new URLSearchParams(window.location.search);
  const token = hashParams.get('token') ?? queryParams.get('token');

  if (!token) return readSession();

  let session: Session | null = null;
  try {
    const profile = await fetchProfile(token);
    session = sessionFromProfile(token, profile.profile ?? {});
    writeSession(session);
  } catch {
    // Invalid or expired handoff token — fall through to any existing session.
    session = null;
  }

  hashParams.delete('token');
  queryParams.delete('token');
  const search = queryParams.toString();
  const hash = hashParams.toString();
  window.history.replaceState(
    null,
    '',
    window.location.pathname + (search ? `?${search}` : '') + (hash ? `#${hash}` : ''),
  );

  return session ?? readSession();
}
