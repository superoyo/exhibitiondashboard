import { Link } from 'react-router-dom';

import { routes } from '@/config/routes';
import { cn } from '@/lib/utils';

/**
 * Brand lockup: the Far East Fame Line mark plus the product name. Served from
 * /logo.png (was /static/logo.png on the legacy pages).
 */
export function Logo({ className, asLink = true }: { className?: string; asLink?: boolean }) {
  const content = (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <img src="/logo.png" alt="Far East Fame Line" className="h-[52px] w-auto" />
      <span>Influencer Real Time Report</span>
    </span>
  );

  if (!asLink) {
    return <span className={cn('text-[0.95rem] font-bold', className)}>{content}</span>;
  }

  return (
    <Link
      to={routes.home}
      className={cn('mr-auto text-[0.95rem] font-bold text-foreground no-underline', className)}
    >
      {content}
    </Link>
  );
}
