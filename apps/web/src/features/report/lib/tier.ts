/**
 * Influencer tier from the follower count.
 *
 * The boundaries are the company's own, from the influencer-campaign-measurement
 * skill's benchmarks (references/benchmarks.md) — the same ladder its ER tables
 * are keyed by, so a tier shown here can be compared against those tables
 * without translation. KOC (<1K) sits below that ladder: real customers whose
 * reviews are bought for authenticity, not reach.
 *
 * Computed at render time from the CURRENT follower count — a creator crossing
 * 10K moves from Nano to Micro on the next refresh. Deliberately not stored:
 * stored tiers go stale, and the roster's own "กลุ่ม" column already holds the
 * team's manual grouping where they want one (tier ≠ กลุ่ม).
 */

export interface Tier {
  code: 'KOC' | 'NANO' | 'MICRO' | 'MACRO' | 'MEGA';
  label: string;
  /** Tailwind classes for the badge — one hue per tier, stronger = bigger. */
  chip: string;
}

// Five rungs, not the benchmark file's six: the team merged Mid into Macro
// (2026-08-19), so Macro spans 100K-1M. When comparing against the ER tables in
// references/benchmarks.md — which still split Mid (100K-500K) from Macro
// (500K-1M) — a 100K-500K account here reads against the Mid row there.
const TIERS: { min: number; tier: Tier }[] = [
  { min: 1_000_000, tier: { code: 'MEGA', label: 'Mega', chip: 'bg-purple-100 text-purple-800' } },
  { min: 100_000, tier: { code: 'MACRO', label: 'Macro', chip: 'bg-blue-100 text-blue-800' } },
  { min: 10_000, tier: { code: 'MICRO', label: 'Micro', chip: 'bg-teal-100 text-teal-800' } },
  { min: 1_000, tier: { code: 'NANO', label: 'Nano', chip: 'bg-emerald-100 text-emerald-800' } },
  { min: 1, tier: { code: 'KOC', label: 'KOC', chip: 'bg-slate-100 text-slate-700' } },
];

/**
 * null when the follower count is unknown. A count of 0 almost always means
 * "not scraped" (private post, audience controls, no refresh yet), and labelling
 * those KOC would file a 946K-follower account under "real customer" the moment
 * one scrape fails. No tier beats a wrong tier.
 */
export function tierOf(followers: number): Tier | null {
  if (!Number.isFinite(followers) || followers <= 0) return null;
  for (const { min, tier } of TIERS) {
    if (followers >= min) return tier;
  }
  return null;
}
