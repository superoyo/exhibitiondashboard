import { platformMeta } from '@/lib/platforms';
import { cn } from '@/lib/utils';

/** Solid pill in the platform's brand colour. */
export function PlatformBadge({
  platform,
  label,
  className,
}: {
  platform: string;
  /** Server-supplied label; falls back to the local platform map. */
  label?: string;
  className?: string;
}) {
  const meta = platformMeta(platform);
  return (
    <span className={cn('chip', className)} style={{ background: meta.color }}>
      {label || meta.label}
    </span>
  );
}
