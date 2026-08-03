/**
 * Platforms a KOL can post on. Records are one row per platform a KOL posted
 * on, so `platform` is a property of a post row — not of the KOL.
 *
 * Mirrors the `PLAT` map in the legacy frontend/report.html; `other` is the
 * fallback bucket for any link we could not classify.
 */
export const PLATFORMS = [
  'tiktok',
  'facebook',
  'instagram',
  'youtube',
  'x',
  'line',
  'website',
  'other',
] as const;

export type Platform = (typeof PLATFORMS)[number];

export function isPlatform(value: unknown): value is Platform {
  return typeof value === 'string' && (PLATFORMS as readonly string[]).includes(value);
}
