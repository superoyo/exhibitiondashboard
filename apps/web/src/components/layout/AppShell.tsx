import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';

import { JobStatusDock } from './JobStatusDock';
import { NavBar, type NavTab } from './NavBar';

/**
 * Standard page frame: centred column, navbar, content. `width` mirrors the
 * per-page max-widths the legacy pages used (the settings page was 3xl, the
 * report pages are much wider).
 */
export function AppShell({
  children,
  tabs,
  width = 'wide',
  className,
}: {
  children: ReactNode;
  tabs?: NavTab[];
  width?: 'narrow' | 'wide';
  className?: string;
}) {
  return (
    <div
      className={cn(
        'mx-auto px-3 py-4 sm:px-5',
        width === 'narrow' ? 'max-w-3xl' : 'max-w-[1400px]',
        className,
      )}
    >
      <NavBar tabs={tabs} />
      {children}
      {/* In the frame, not on one page: a job outlives the page that started
          it. The client-facing view returns before reaching AppShell, so this
          never shows to a client. */}
      <JobStatusDock />
    </div>
  );
}
