import { lazy, Suspense } from 'react';
import { createBrowserRouter, Navigate, Outlet } from 'react-router-dom';

import { legacyCampaignAliases, routes } from '@/config/routes';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { RequireAuth } from '@/features/auth/components/RequireAuth';

const LoginPage = lazy(() => import('@/features/auth/pages/LoginPage'));
const HomePage = lazy(() => import('@/features/campaigns/pages/HomePage'));
const RosterPage = lazy(() => import('@/features/roster/pages/RosterPage'));
const TrackerPage = lazy(() => import('@/features/tracker/pages/TrackerPage'));
const TokenPage = lazy(() => import('@/features/settings/pages/TokenPage'));
const CampaignReportPage = lazy(() => import('@/features/report/pages/CampaignReportPage'));
const PublicReportPage = lazy(() => import('@/features/report/pages/PublicReportPage'));
const NotFoundPage = lazy(() => import('@/app/NotFoundPage'));

function Fallback() {
  return <div className="mt-[20vh] text-center text-sm text-muted-foreground">กำลังโหลด…</div>;
}

function Root() {
  return (
    <ErrorBoundary>
      <Suspense fallback={<Fallback />}>
        <Outlet />
      </Suspense>
    </ErrorBoundary>
  );
}

/**
 * Every page is React now.
 *
 * Two groups that must not be confused:
 *  - PUBLIC: `/login` and the `/v/...` client report links. The `/v` routes sit
 *    OUTSIDE RequireAuth on purpose — clients have no session, and wrapping them
 *    would turn every shared report link into a login wall.
 *  - GUARDED: everything else.
 *
 * The legacy single-campaign paths (`/report`, `/sahagroup`, `/sahagroup2027`)
 * redirect to their `/c/<key>` equivalent so old bookmarks keep working.
 */
export const router = createBrowserRouter([
  {
    element: <Root />,
    children: [
      // ---- public ----
      { path: routes.login, element: <LoginPage /> },
      { path: routes.viewPattern, element: <PublicReportPage /> },
      { path: routes.viewNamedPattern, element: <PublicReportPage /> },

      // ---- guarded ----
      {
        element: <RequireAuth />,
        children: [
          { path: routes.home, element: <HomePage /> },
          { path: routes.campaignPattern, element: <CampaignReportPage /> },
          { path: routes.roster, element: <RosterPage /> },
          { path: routes.tracker, element: <TrackerPage /> },
          { path: routes.settings, element: <TokenPage /> },

          ...Object.entries(legacyCampaignAliases).map(([path, key]) => ({
            path,
            element: <Navigate to={routes.campaign(key)} replace />,
          })),
        ],
      },

      { path: '*', element: <NotFoundPage /> },
    ],
  },
]);
