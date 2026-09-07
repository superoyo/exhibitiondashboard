import type { LucideIcon } from 'lucide-react';
import {
  Facebook,
  Globe,
  Instagram,
  Link as LinkIcon,
  MessageCircle,
  Music2,
  X as XIcon,
  Youtube,
} from 'lucide-react';

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

const PLATFORM_ICONS: Record<string, LucideIcon> = {
  tiktok: Music2,
  facebook: Facebook,
  instagram: Instagram,
  youtube: Youtube,
  x: XIcon,
  line: MessageCircle,
  website: Globe,
  other: LinkIcon,
};

/**
 * Compact round brand icon — the posts table swapped its text pills for these
 * when wide campaigns pushed the columns off-screen (team ask, 2026-09-07).
 * With `href` the icon IS the post link (and replaces the old far-right
 * "เปิด ↗" column); without one it renders muted — "ยังไม่มีลิงก์โพสต์".
 */
export function PlatformIcon({
  platform,
  label,
  href,
}: {
  platform: string;
  label?: string;
  /** Post URL — when present the icon opens the post in a new tab. */
  href?: string;
}) {
  const meta = platformMeta(platform);
  const Icon = PLATFORM_ICONS[platform || 'other'] ?? LinkIcon;
  const name = label || meta.label;
  const body = (
    <span
      className="inline-flex size-6 flex-none items-center justify-center rounded-full text-white"
      style={{ background: meta.color }}
    >
      <Icon aria-hidden="true" className="size-3.5" strokeWidth={2.5} />
    </span>
  );
  if (href) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        title={`${name} — เปิดโพสต์ในแท็บใหม่`}
        aria-label={`เปิดโพสต์ ${name}`}
        className="relative inline-flex rounded-full align-middle transition hover:scale-110 hover:ring-2 hover:ring-black/25"
      >
        {body}
        {/* Corner ↗ so a glance says "this opens the post" (team ask). */}
        <span
          aria-hidden="true"
          className="absolute -right-1 -top-1 flex size-3.5 items-center justify-center rounded-full border border-border bg-white text-[9px] font-bold leading-none text-slate-700 shadow-sm"
        >
          ↗
        </span>
      </a>
    );
  }
  return (
    <span title={`${name} — ยังไม่มีลิงก์โพสต์`} className="inline-flex align-middle opacity-40">
      {body}
    </span>
  );
}
