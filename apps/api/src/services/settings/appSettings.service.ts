import { eq } from 'drizzle-orm';

import { db } from '../../config/database.js';
import { logger } from '../../config/logger.js';
import { appSettings } from '../../models/schema.js';

/**
 * Runtime-editable settings, stored in `app_settings`.
 *
 * Used for the Apify token and Claude key (so an expired key can be swapped from
 * the web UI without a redeploy), the accumulated per-campaign Apify cost, and
 * each campaign's linked source spreadsheet.
 */

/**
 * Reads never throw.
 *
 * Ported deliberately from Python's `get_setting`, which swallows database
 * errors and returns None: these values are read on paths that must degrade
 * rather than fail (e.g. the token lookup inside a scrape), so a transient DB
 * hiccup should not turn into a 500.
 */
export async function getSetting(key: string): Promise<string | null> {
  try {
    const rows = await db
      .select({ value: appSettings.value })
      .from(appSettings)
      .where(eq(appSettings.key, key))
      .limit(1);
    return rows[0]?.value ?? null;
  } catch (err) {
    logger.warn({ err, key }, 'getSetting failed');
    return null;
  }
}

/** Upsert. Unlike reads, a failed write must surface to the caller. */
export async function setSetting(key: string, value: string): Promise<void> {
  await db
    .insert(appSettings)
    .values({ key, value })
    .onConflictDoUpdate({ target: appSettings.key, set: { value } });
}

export async function deleteSetting(key: string): Promise<void> {
  await db.delete(appSettings).where(eq(appSettings.key, key));
}
