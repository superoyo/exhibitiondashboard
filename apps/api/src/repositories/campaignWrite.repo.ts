import { randomBytes } from 'node:crypto';
import { eq } from 'drizzle-orm';

import { db } from '../config/database.js';
import { appSettings, campaigns, reportKols, reportPosts } from '../models/schema.js';
import type { CampaignRow } from './campaign.repo.js';

/**
 * Client view token.
 *
 * `secrets.token_urlsafe(9)` on the Python side: 9 random bytes rendered
 * base64url, i.e. 12 characters. Matched exactly so tokens issued by either
 * service look the same.
 */
export function newViewToken(): string {
  return randomBytes(9).toString('base64url');
}

/** Numeric keys only, so legacy string keys (pao/sahagroup) don't affect numbering. */
export async function nextNumericKey(): Promise<string> {
  const rows = await db.select({ key: campaigns.key }).from(campaigns);
  const numbers = rows
    .map((r) => r.key)
    .filter((k) => /^\d+$/.test(k))
    .map((k) => Number.parseInt(k, 10));

  // Based on the max across ALL campaigns including archived ones, so a code is
  // never reused after a campaign is deleted.
  let n = numbers.length ? Math.max(...numbers) + 1 : 1;
  const existing = new Set(rows.map((r) => r.key));
  let key = String(n).padStart(5, '0');
  while (existing.has(key)) {
    n += 1;
    key = String(n).padStart(5, '0');
  }
  return key;
}

/**
 * Friendly URL key from a campaign name.
 * 'Bon (2026-061) DNA High Protein' -> 'bon-2026-061-dna-high-protein'
 *
 * Thai-only names collapse to an empty slug (keys allow a-z/0-9/- only); the
 * caller then falls back to a running number.
 */
export function slugFromName(name: string): string {
  const s = (name || '').toLowerCase().replace(/[^a-z0-9]+/g, '-');
  return s
    .replace(/-+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 32)
    .replace(/^-+|-+$/g, '');
}

/** Unique key for a new campaign: slug, else slug-2/-3…, else a running code. */
export async function keyForName(name: string): Promise<string> {
  const base = slugFromName(name);
  if (!base || /^\d+$/.test(base)) return nextNumericKey();

  const existing = new Set(
    (await db.select({ key: campaigns.key }).from(campaigns)).map((r) => r.key),
  );
  if (!existing.has(base)) return base;

  let n = 2;
  for (;;) {
    const suffix = `-${String(n)}`;
    const candidate = base.slice(0, 32 - suffix.length) + suffix;
    if (!existing.has(candidate)) return candidate;
    n += 1;
  }
}

export async function insertCampaign(values: {
  key: string;
  name: string;
  emoji: string;
  subtitle: string | null;
  groupsJson: string;
  subgroupsJson: string;
  viewToken: string;
  createdBy: string | null;
  createdByPhoto: string | null;
}): Promise<CampaignRow> {
  const rows = await db
    .insert(campaigns)
    .values({ ...values, active: true })
    .returning();
  const row = rows[0];
  if (!row) throw new Error('insert returned no row');
  return row;
}

export async function updateCampaign(
  key: string,
  patch: Partial<{
    name: string;
    emoji: string;
    subtitle: string | null;
    groupsJson: string;
    subgroupsJson: string;
    active: boolean;
  }>,
): Promise<CampaignRow | undefined> {
  const rows = await db.update(campaigns).set(patch).where(eq(campaigns.key, key)).returning();
  return rows[0];
}

/** Soft delete: KOL data and the URL survive; the card leaves the home grid. */
export async function archiveCampaign(key: string): Promise<boolean> {
  const rows = await db
    .update(campaigns)
    .set({ active: false })
    .where(eq(campaigns.key, key))
    .returning({ key: campaigns.key });
  return rows.length > 0;
}

export async function ensureViewToken(key: string): Promise<string | null> {
  const rows = await db
    .select({ token: campaigns.viewToken })
    .from(campaigns)
    .where(eq(campaigns.key, key))
    .limit(1);
  if (!rows.length) return null;

  const existing = rows[0]?.token;
  if (existing) return existing;

  const token = newViewToken();
  await db.update(campaigns).set({ viewToken: token }).where(eq(campaigns.key, key));
  return token;
}

/** Settings keys that are namespaced per campaign and must follow a rename. */
const CAMPAIGN_SETTING_PREFIXES = ['refresh_cost:', 'sheet_url:'] as const;

/**
 * Change a campaign's URL key everywhere.
 *
 * `campaign` is a soft link (no foreign key), so nothing cascades on its own —
 * report_kols, report_posts and the per-campaign settings rows must all be
 * rewritten. Done in ONE transaction: a partial rename would orphan a
 * campaign's entire roster and post history.
 */
export async function renameCampaign(oldKey: string, newKey: string): Promise<void> {
  await db.transaction(async (tx) => {
    await tx.update(campaigns).set({ key: newKey }).where(eq(campaigns.key, oldKey));
    await tx.update(reportKols).set({ campaign: newKey }).where(eq(reportKols.campaign, oldKey));
    await tx.update(reportPosts).set({ campaign: newKey }).where(eq(reportPosts.campaign, oldKey));

    for (const prefix of CAMPAIGN_SETTING_PREFIXES) {
      const from = `${prefix}${oldKey}`;
      const to = `${prefix}${newKey}`;
      const old = await tx
        .select({ value: appSettings.value })
        .from(appSettings)
        .where(eq(appSettings.key, from))
        .limit(1);
      if (!old.length) continue;

      const value = old[0]?.value ?? null;
      // Upsert onto the new key, then drop the old one — matching Python, which
      // overwrites an existing destination row rather than failing.
      await tx
        .insert(appSettings)
        .values({ key: to, value })
        .onConflictDoUpdate({ target: appSettings.key, set: { value } });
      await tx.delete(appSettings).where(eq(appSettings.key, from));
    }
  });
}

/** True when a campaign key is already taken. */
export async function keyExists(key: string): Promise<boolean> {
  const rows = await db
    .select({ key: campaigns.key })
    .from(campaigns)
    .where(eq(campaigns.key, key))
    .limit(1);
  return rows.length > 0;
}
