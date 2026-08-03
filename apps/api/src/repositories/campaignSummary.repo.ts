import { and, countDistinct, count, eq, gte, isNotNull, max, sum } from 'drizzle-orm';

import { db } from '../config/database.js';
import { campaigns, reportKols, reportPosts } from '../models/schema.js';

/**
 * Aggregates behind `GET /api/campaigns/summary`.
 *
 * `days > 0` restricts to posts PUBLISHED in the last N days (by `posted_at`).
 * Two consequences, both inherited from the Python implementation and both
 * documented in its docstring:
 *   - it is NOT "views gained in that window" — report_posts holds a snapshot of
 *     each post's latest totals, so a per-day delta cannot be derived
 *   - posts with a null `posted_at` are EXCLUDED when a window is given, since
 *     we cannot tell whether they fall inside it
 */
function windowStart(days: number): Date | null {
  if (!days) return null;
  return new Date(Date.now() - days * 24 * 60 * 60 * 1000);
}

/** Active roster size per campaign (whole roster, ignoring the window). */
export async function kolCounts(): Promise<Map<string, number>> {
  const rows = await db
    .select({ campaign: reportKols.campaign, n: count() })
    .from(reportKols)
    .where(eq(reportKols.active, true))
    .groupBy(reportKols.campaign);
  return new Map(rows.map((r) => [r.campaign, Number(r.n)]));
}

/**
 * Total views per campaign, counted the way the report page does: take the
 * top-viewed post per (username, platform), then sum those.
 *
 * Summing every post would double-count a KOL who posted several times, which
 * is why this is a two-level aggregate rather than a plain SUM.
 */
export async function viewTotals(days: number): Promise<Map<string, number>> {
  const since = windowStart(days);
  const filter = since
    ? and(isNotNull(reportPosts.postedAt), gte(reportPosts.postedAt, since.toISOString()))
    : undefined;

  const best = db
    .select({
      campaign: reportPosts.campaign,
      views: max(reportPosts.views).as('views'),
    })
    .from(reportPosts)
    .where(filter)
    .groupBy(reportPosts.campaign, reportPosts.username, reportPosts.platform)
    .as('best');

  const rows = await db
    .select({ campaign: best.campaign, total: sum(best.views) })
    .from(best)
    .groupBy(best.campaign);

  return new Map(rows.map((r) => [r.campaign, Number(r.total ?? 0)]));
}

/** Post count per campaign within the window. */
export async function postCounts(days: number): Promise<Map<string, number>> {
  const since = windowStart(days);
  const rows = await db
    .select({ campaign: reportPosts.campaign, n: count() })
    .from(reportPosts)
    .where(
      since
        ? and(isNotNull(reportPosts.postedAt), gte(reportPosts.postedAt, since.toISOString()))
        : undefined,
    )
    .groupBy(reportPosts.campaign);
  return new Map(rows.map((r) => [r.campaign, Number(r.n)]));
}

/**
 * KOLs who actually posted inside the window — distinct from `kolCounts`, which
 * is the whole roster.
 */
export async function activeKolCounts(days: number): Promise<Map<string, number>> {
  const since = windowStart(days);
  const rows = await db
    .select({ campaign: reportPosts.campaign, n: countDistinct(reportPosts.username) })
    .from(reportPosts)
    .where(
      since
        ? and(isNotNull(reportPosts.postedAt), gte(reportPosts.postedAt, since.toISOString()))
        : undefined,
    )
    .groupBy(reportPosts.campaign);
  return new Map(rows.map((r) => [r.campaign, Number(r.n)]));
}

/**
 * Campaigns to report on. When `keys` is given, archived campaigns are INCLUDED
 * — an external consumer asking for a specific key wants it regardless of state.
 */
export async function campaignsForSummary(keys: string[]) {
  const rows = await db.select().from(campaigns);
  if (!keys.length) return rows;
  const wanted = new Set(keys);
  return rows.filter((r) => wanted.has(r.key));
}
