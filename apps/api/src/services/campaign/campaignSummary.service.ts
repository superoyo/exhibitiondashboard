import type { CampaignSummaryResponse } from '@kol/shared';

import { lastScrapedAt } from '../../repositories/campaign.repo.js';
import * as repo from '../../repositories/campaignSummary.repo.js';
import { toIsoLocal } from '../../utils/dates.js';

/**
 * `GET /api/campaigns/summary` — lightweight per-campaign totals for external
 * consumers (Agency Intelligence), so they don't have to pull the whole
 * `/report/data` payload and count it themselves.
 *
 * `total_views` matches the report page: the top-viewed post per
 * (username, platform), summed. Not every post — that would overstate any KOL
 * who posted more than once.
 */
export async function campaignSummary(
  keys: string[],
  days: number,
): Promise<CampaignSummaryResponse> {
  const [rows, kolCounts, viewTotals, postCounts, activeKols, lastSeen] = await Promise.all([
    repo.campaignsForSummary(keys),
    repo.kolCounts(),
    repo.viewTotals(days),
    repo.postCounts(days),
    repo.activeKolCounts(days),
    // Deliberately the UN-windowed "last scraped" map: Python does the same, so
    // refreshed_at is not affected by `days`.
    lastScrapedAt(),
  ]);

  const campaigns = rows
    .map((row) => ({
      key: row.key,
      name: row.name,
      active: row.active,
      kol_count: kolCounts.get(row.key) ?? 0,
      active_kol_count: activeKols.get(row.key) ?? 0,
      post_count: postCounts.get(row.key) ?? 0,
      total_views: viewTotals.get(row.key) ?? 0,
      refreshed_at: toIsoLocal(lastSeen.get(row.key) ?? null),
    }))
    .sort((a, b) => (a.key > b.key ? 1 : a.key < b.key ? -1 : 0));

  // Python emits `days or None`, so 0 becomes null rather than 0.
  return { window_days: days || null, campaigns };
}
