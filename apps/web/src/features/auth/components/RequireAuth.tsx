import { Navigate, Outlet, useLocation } from 'react-router-dom';

import { useAppSelector } from '@/app/store';
import { isPublicPath, routes } from '@/config/routes';

/**
 * Route guard for every page that needs a signed-in employee.
 *
 * Public client reports (`/v/:token`) are NOT wrapped in this — they must open
 * with no session at all. See MIGRATION_PLAN.md §6.4.
 */
export function RequireAuth() {
  const { session, ready } = useAppSelector((s) => s.auth);
  const location = useLocation();

  // The SSO handoff resolves before the first render, so `ready` is normally
  // already true here; this guard just prevents a redirect flash if it is not.
  if (!ready) return null;

  // `?view=1` forces client/preview mode and must bypass the guard, exactly as
  // the legacy auth.js did — otherwise a shared preview link becomes a login
  // wall for someone who has no account.
  if (isPublicPath(location.pathname, location.search)) return <Outlet />;

  if (!session) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`${routes.login}?next=${next}`} replace />;
  }

  return <Outlet />;
}
