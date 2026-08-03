import { and, count, desc, eq, isNotNull, max } from 'drizzle-orm';

import { db } from '../config/database.js';
import { campaigns, reportKols, reportPosts } from '../models/schema.js';

export type CampaignRow = typeof campaigns.$inferSelect;

/** Latest N campaigns, newest first. */
export async function listCampaigns(
  limit: number,
  includeInactive: boolean,
): Promise<CampaignRow[]> {
  const query = db.select().from(campaigns);
  const filtered = includeInactive ? query : query.where(eq(campaigns.active, true));
  return filtered.orderBy(desc(campaigns.createdAt)).limit(limit);
}

export async function getCampaign(key: string): Promise<CampaignRow | undefined> {
  const rows = await db.select().from(campaigns).where(eq(campaigns.key, key)).limit(1);
  return rows[0];
}

export async function findByViewToken(token: string): Promise<CampaignRow | undefined> {
  const rows = await db.select().from(campaigns).where(eq(campaigns.viewToken, token)).limit(1);
  return rows[0];
}

/**
 * Active roster size per campaign, as one grouped query.
 *
 * Deliberately not per-campaign lookups: the home grid shows up to 100 cards and
 * that would be 100 round-trips.
 */
export async function activeRosterCounts(): Promise<Map<string, number>> {
  const rows = await db
    .select({ campaign: reportKols.campaign, n: count() })
    .from(reportKols)
    .where(eq(reportKols.active, true))
    .groupBy(reportKols.campaign);
  return new Map(rows.map((r) => [r.campaign, Number(r.n)]));
}

/**
 * Most recent post-scrape time per campaign.
 *
 * Returned as Postgres' own text (see utils/dates.ts) — not a Date — so the
 * offset and microseconds survive intact.
 */
export async function lastScrapedAt(): Promise<Map<string, string>> {
  const rows = await db
    .select({ campaign: reportPosts.campaign, last: max(reportPosts.scrapedAt) })
    .from(reportPosts)
    .groupBy(reportPosts.campaign);
  return new Map(rows.flatMap((r) => (r.last ? [[r.campaign, r.last] as [string, string]] : [])));
}

/** Roster size for one campaign. */
export async function rosterCount(key: string): Promise<number> {
  const rows = await db
    .select({ n: count() })
    .from(reportKols)
    .where(and(eq(reportKols.campaign, key), eq(reportKols.active, true)));
  return Number(rows[0]?.n ?? 0);
}

/** Latest scrape time for one campaign. */
export async function lastScrapedFor(key: string): Promise<string | null> {
  const rows = await db
    .select({ last: max(reportPosts.scrapedAt) })
    .from(reportPosts)
    .where(eq(reportPosts.campaign, key));
  return rows[0]?.last ?? null;
}

/**
 * Posts that still have a tie-in marker but no cached image — the "no product
 * found" markers that a new pack shot makes eligible for a retry.
 */
export async function postsWithTieinMarker(key: string) {
  return db
    .select({ id: reportPosts.id, tieinHash: reportPosts.tieinHash })
    .from(reportPosts)
    .where(and(eq(reportPosts.campaign, key), isNotNull(reportPosts.tieinHash)));
}
