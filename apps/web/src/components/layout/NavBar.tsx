import { NavLink } from 'react-router-dom';

import { routes } from '@/config/routes';
import { cn } from '@/lib/utils';
import { UserChip } from '@/features/auth/components/UserChip';

import { GlobalMenuSlot } from './GlobalMenuSlot';
import { Logo } from './Logo';

export interface NavTab {
  to: string;
  label: string;
  /** Match only the exact path (used for "← Home"). */
  end?: boolean;
}

/**
 * Navbar shell. Tabs are passed in per page rather than hardcoded here, because
 * the legacy pages each showed a different subset.
 */
export function NavBar({ tabs = [] }: { tabs?: NavTab[] }) {
  return (
    <nav className="mb-4 flex flex-wrap items-center gap-1.5">
      <GlobalMenuSlot />
      <Logo />
      {tabs.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          end={tab.end}
          className={({ isActive }) => cn('navtab', isActive && 'navtab-active')}
        >
          {tab.label}
        </NavLink>
      ))}
      <UserChip />
    </nav>
  );
}

/** Tabs shown by the settings page. */
export const SETTINGS_TABS: NavTab[] = [
  { to: routes.home, label: '← Home', end: true },
  { to: routes.settings, label: 'Apify Token' },
];
