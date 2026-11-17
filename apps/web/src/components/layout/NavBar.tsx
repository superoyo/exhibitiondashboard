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

/**
 * The top-level menu, in one place. Home, KOL List and the settings page each
 * kept their own copy of this list, so a new page had to be added three times
 * — and was reachable only from the copies someone remembered to edit.
 */
export const MAIN_TABS: NavTab[] = [
  { to: routes.home, label: 'Home', end: true },
  { to: routes.promo, label: 'Promotion Page Package' },
  { to: routes.kolList, label: 'KOL List' },
  { to: routes.settings, label: 'Apify Token' },
];

/** Tabs shown by the settings page — the main menu with a "← Home" back label. */
export const SETTINGS_TABS: NavTab[] = MAIN_TABS.map((tab) =>
  tab.to === routes.home ? { ...tab, label: '← Home' } : tab,
);
