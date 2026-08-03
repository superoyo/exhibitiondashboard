import type { Platform } from '@kol/shared';

/**
 * Per-platform badge label + brand colour. Ported from the legacy `PLAT` map;
 * `other` is the label used for links we could not classify.
 */
export const PLATFORM_META: Record<Platform, { label: string; color: string }> = {
  tiktok: { label: 'TikTok', color: '#111111' },
  facebook: { label: 'Facebook', color: '#1877f2' },
  instagram: { label: 'Instagram', color: '#c13584' },
  youtube: { label: 'YouTube', color: '#ff0000' },
  x: { label: 'X', color: '#111111' },
  line: { label: 'LINE', color: '#06c755' },
  website: { label: 'Website', color: '#0ea5e9' },
  other: { label: 'ลิงก์', color: '#64748b' },
};

export function platformMeta(platform: string | null | undefined) {
  return PLATFORM_META[(platform ?? 'other') as Platform] ?? PLATFORM_META.other;
}
