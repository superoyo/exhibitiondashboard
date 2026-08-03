/**
 * Campaign metadata — powers the home-page grid and the report header.
 * Shape mirrors `_campaign_dict()` in app/api/routes.py:770.
 */
export interface Campaign {
  key: string;
  name: string;
  /** Always populated; the backend defaults it to a chart emoji. */
  emoji: string;
  subtitle: string;
  groups: string[];
  subgroups: string[];
  active: boolean;
  /** ISO timestamp, or null when unset. */
  created_at: string | null;
  roster_count: number;
  /** Latest post-scrape time — drives the "data as of" line. */
  refreshed_at: string | null;

  /**
   * Creator attribution. Present ONLY on the auth-protected list endpoint —
   * the open single-campaign GET used by public client pages omits it on
   * purpose, so treat both as optional.
   */
  created_by?: string | null;
  created_by_photo?: string | null;
}

export interface CampaignCreateInput {
  name: string;
  emoji?: string;
  subtitle?: string;
  groups?: string[];
  subgroups?: string[];
}

export type CampaignPatchInput = Partial<
  Pick<Campaign, 'name' | 'emoji' | 'subtitle' | 'groups' | 'subgroups' | 'active'>
>;

/** `GET /api/campaigns` */
export interface CampaignListResponse {
  campaigns: Campaign[];
}

/** `GET /api/campaigns/:key/view-token` — note the field is `token`. */
export interface ViewTokenResponse {
  token: string;
}

/**
 * `DELETE /api/campaigns/:key` — a SOFT delete: the campaign is archived
 * (active=false) so KOL data survives and the URL keeps working. The UI copy
 * must not promise permanent deletion.
 */
export interface CampaignArchiveResponse {
  status: 'archived';
  key: string;
}

/** `POST /api/campaigns/:key/rename` — `key` is the new key. */
export interface CampaignRenameResponse {
  status: 'renamed' | 'unchanged';
  key: string;
}

/**
 * `GET /api/campaigns/summary` — lightweight per-campaign totals for external
 * consumers. `total_views` counts the top-viewed post per (username, platform),
 * matching the report page rather than summing every post.
 */
export interface CampaignSummary {
  key: string;
  name: string;
  active: boolean;
  kol_count: number;
  active_kol_count: number;
  post_count: number;
  total_views: number;
  refreshed_at: string | null;
}

export interface CampaignSummaryResponse {
  window_days: number | null;
  campaigns: CampaignSummary[];
}
