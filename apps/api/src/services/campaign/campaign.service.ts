import type { Campaign } from '@kol/shared';

import { logger } from '../../config/logger.js';
import * as repo from '../../repositories/campaign.repo.js';
import type { CampaignRow } from '../../repositories/campaign.repo.js';
import { AppError } from '../../utils/AppError.js';
import { toIsoLocal } from '../../utils/dates.js';

/** Parse a JSON text column, tolerating legacy rows that hold malformed data. */
function parseJsonArray(raw: string | null): string[] {
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as string[]) : [];
  } catch {
    logger.warn({ raw }, 'Malformed JSON array column; treating as empty');
    return [];
  }
}

/**
 * Serialise a campaign row for the API.
 *
 * Mirrors `_campaign_dict()` in app/api/routes.py:770 exactly, including the
 * emoji default and the null→'' coercion on `subtitle`.
 */
export function serializeCampaign(
  row: CampaignRow,
  rosterCount = 0,
  refreshedAt: string | null = null,
): Campaign {
  return {
    key: row.key,
    name: row.name,
    emoji: row.emoji || '📊',
    subtitle: row.subtitle ?? '',
    groups: parseJsonArray(row.groupsJson),
    subgroups: parseJsonArray(row.subgroupsJson),
    active: row.active,
    created_at: toIsoLocal(row.createdAt),
    roster_count: rosterCount,
    refreshed_at: toIsoLocal(refreshedAt),
  };
}

/**
 * Home-page grid. Roster counts and last-scrape times are fetched as two
 * grouped queries rather than per campaign.
 *
 * `created_by` is attached here but NOT by `getCampaignDetail`: this endpoint is
 * auth-protected, while the single-campaign GET is open to view-only client
 * pages and must not leak who created the report.
 */
export async function listCampaigns(limit: number, includeInactive: boolean) {
  const [rows, counts, lastSeen] = await Promise.all([
    repo.listCampaigns(limit, includeInactive),
    repo.activeRosterCounts(),
    repo.lastScrapedAt(),
  ]);

  return rows.map((row) => ({
    ...serializeCampaign(row, counts.get(row.key) ?? 0, lastSeen.get(row.key) ?? null),
    created_by: row.createdBy,
    created_by_photo: row.createdByPhoto,
  }));
}

export async function getCampaignDetail(key: string): Promise<Campaign> {
  const row = await repo.getCampaign(key);
  if (!row) throw AppError.notFound(`ไม่พบแคมเปญ '${key}'`);

  const [rosterCount, refreshedAt] = await Promise.all([
    repo.rosterCount(key),
    repo.lastScrapedFor(key),
  ]);
  return serializeCampaign(row, rosterCount, refreshedAt);
}
