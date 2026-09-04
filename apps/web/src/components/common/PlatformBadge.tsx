import { platformMeta } from '@/lib/platforms';
import { cn } from '@/lib/utils';

/** Solid pill in the platform's brand colour. Give it `href` and the pill
 *  itself opens the post in a new tab (with a ↗ marker) — the team couldn't
 *  find the link when it only lived in the table's far-right column, which a
 *  dense table pushes off-screen (2026-09-04). */
export function PlatformBadge({
  platform,
  label,
  className,
  href,
}: {
  platform: string;
  /** Server-supplied label; falls back to the local platform map. */
  label?: string;
  className?: string;
  /** Post URL — when present the badge becomes the link to the post. */
  href?: string;
}) {
  const meta = platformMeta(platform);
  if (href) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        title="เปิดโพสต์ในแท็บใหม่"
        className={cn(
          'chip whitespace-nowrap transition hover:opacity-80 hover:ring-2 hover:ring-black/20',
          className,
        )}
        style={{ background: meta.color }}
      >
        {label || meta.label} ↗
      </a>
    );
  }
  return (
    <span className={cn('chip whitespace-nowrap', className)} style={{ background: meta.color }}>
      {label || meta.label}
    </span>
  );
}
