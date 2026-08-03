import { and, asc, eq, max } from 'drizzle-orm';

import { db } from '../config/database.js';
import { kols, reportKols } from '../models/schema.js';

export type TrackerKolRow = typeof kols.$inferSelect;
export type ReportKolRow = typeof reportKols.$inferSelect;

/**
 * Two independent rosters:
 *   - `tracker` (`kols`)       — one global list, fixed groups, no post links
 *   - `report`  (`report_kols`) — per-campaign, with post links and a subgroup
 *
 * Their columns differ, so they are handled separately rather than behind a
 * shared abstraction that would have to lie about which fields exist.
 */

/** Tracker roster, ordered by group then username (as Python does). */
export async function listTracker(): Promise<TrackerKolRow[]> {
  return db.select().from(kols).orderBy(asc(kols.contentGroup), asc(kols.username));
}

/** Report roster, ordered by the imported file's row order. */
export async function listReport(campaign: string): Promise<ReportKolRow[]> {
  return db
    .select()
    .from(reportKols)
    .where(eq(reportKols.campaign, campaign))
    .orderBy(asc(reportKols.sortOrder), asc(reportKols.id));
}

export async function findTrackerByUsername(username: string): Promise<TrackerKolRow | undefined> {
  const rows = await db.select().from(kols).where(eq(kols.username, username)).limit(1);
  return rows[0];
}

export async function findReportByUsername(
  campaign: string,
  username: string,
): Promise<ReportKolRow | undefined> {
  const rows = await db
    .select()
    .from(reportKols)
    .where(and(eq(reportKols.campaign, campaign), eq(reportKols.username, username)))
    .limit(1);
  return rows[0];
}

export async function insertTracker(values: {
  username: string;
  display: string;
  contentGroup: string;
}): Promise<TrackerKolRow> {
  const rows = await db
    .insert(kols)
    .values({ ...values, active: true })
    .returning();
  const row = rows[0];
  if (!row) throw new Error('insert returned no row');
  return row;
}

/** Next sort_order for a campaign: max + 1, so new rows land at the end. */
export async function nextSortOrder(campaign: string): Promise<number> {
  const rows = await db
    .select({ maxOrder: max(reportKols.sortOrder) })
    .from(reportKols)
    .where(eq(reportKols.campaign, campaign));
  return (rows[0]?.maxOrder ?? 0) + 1;
}

export async function insertReport(values: {
  username: string;
  display: string;
  contentGroup: string;
  campaign: string;
  sortOrder: number;
  subgroup?: string | null;
  url?: string | null;
}): Promise<ReportKolRow> {
  const rows = await db
    .insert(reportKols)
    .values({ ...values, active: true })
    .returning();
  const row = rows[0];
  if (!row) throw new Error('insert returned no row');
  return row;
}

export async function getTracker(id: number): Promise<TrackerKolRow | undefined> {
  const rows = await db.select().from(kols).where(eq(kols.id, id)).limit(1);
  return rows[0];
}

export async function getReport(id: number): Promise<ReportKolRow | undefined> {
  const rows = await db.select().from(reportKols).where(eq(reportKols.id, id)).limit(1);
  return rows[0];
}

export async function updateTracker(
  id: number,
  patch: Partial<{ display: string; contentGroup: string; active: boolean }>,
): Promise<TrackerKolRow | undefined> {
  if (!Object.keys(patch).length) return getTracker(id);
  const rows = await db.update(kols).set(patch).where(eq(kols.id, id)).returning();
  return rows[0];
}

export async function updateReport(
  id: number,
  patch: Partial<{
    display: string;
    contentGroup: string;
    active: boolean;
    subgroup: string | null;
    linksJson: string | null;
    url: string | null;
  }>,
): Promise<ReportKolRow | undefined> {
  if (!Object.keys(patch).length) return getReport(id);
  const rows = await db.update(reportKols).set(patch).where(eq(reportKols.id, id)).returning();
  return rows[0];
}

export async function deleteTracker(id: number): Promise<boolean> {
  const rows = await db.delete(kols).where(eq(kols.id, id)).returning({ id: kols.id });
  return rows.length > 0;
}

export async function deleteReport(id: number): Promise<boolean> {
  const rows = await db
    .delete(reportKols)
    .where(eq(reportKols.id, id))
    .returning({ id: reportKols.id });
  return rows.length > 0;
}

/**
 * Replace a campaign's whole roster in one transaction.
 *
 * REPLACE, never append — a re-upload of the same sheet must not double every
 * row. Wrapped in a transaction because a failure between the delete and the
 * inserts would leave the campaign with no roster at all.
 */
export async function replaceReportRoster(
  campaign: string,
  rows: Array<{
    username: string;
    display: string;
    contentGroup: string;
    subgroup: string | null;
    url: string | null;
    linksJson: string | null;
    followers: number;
    sortOrder: number;
  }>,
): Promise<number> {
  return db.transaction(async (tx) => {
    await tx.delete(reportKols).where(eq(reportKols.campaign, campaign));
    if (rows.length) {
      await tx.insert(reportKols).values(rows.map((r) => ({ ...r, campaign, active: true })));
    }
    return rows.length;
  });
}
