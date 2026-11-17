/**
 * Promotion Page Package — read-only quota overview (`/api/promo/*`).
 *
 * Clients pre-buy posting quotas on Facebook promotion pages; each team member
 * tracks their deals in their own sheet, and the server reads those sheets
 * into the shapes below (app/promo_sheet.py). Counts and links only — money
 * columns are deliberately never read.
 */

/**
 * used     — the team marked it posted, or a post link is present
 * reserved — names a brand/job but is not posted yet
 * free     — an empty row of the bought quota
 */
export type PromoSlotStatus = 'used' | 'reserved' | 'free';

export interface PromoLink {
  platform: string;
  url: string;
}

/** One bought post ("Sale Here 7"). Text fields are as the team wrote them. */
export interface PromoSlot {
  n: number;
  status: PromoSlotStatus;
  /** The sheet's own status word when it is not a plain "posted" ("Wait idea"). */
  status_text: string;
  account: string;
  campaign: string;
  buyer: string;
  /** As written; `date_iso` is set only when the cell was a real date. */
  date: string;
  date_iso: string | null;
  links: PromoLink[];
  note: string;
  /** Banner row the slot sits under in the sheet ("SALZ"), or ''. */
  section: string;
}

export interface PromoCounts {
  quota: number;
  used: number;
  reserved: number;
  free: number;
}

export interface PromoPackSummary extends PromoCounts {
  /** The promotion page the quota was bought on. */
  page: string;
  /** ISO date, or free text ("ระยะการใช้ 6 เดือนนับจากใช้ครั้งแรก"), or ''. */
  expiry: string;
}

export interface PromoPack extends PromoPackSummary {
  slots: PromoSlot[];
}

export interface PromoCampaignSummary extends PromoCounts {
  id: number;
  name: string;
  team: string;
  sheet_url: string;
  /** Last successful read of the sheet; null = never read. */
  synced_at: string | null;
  /** Why the latest read failed. The numbers shown are the last good ones. */
  sync_error: string | null;
  created_by: string | null;
  created_at: string | null;
  pack_count: number;
  /** Every bought post is used. False for a deal that has never been read. */
  complete: boolean;
  packs: PromoPackSummary[];
}

export interface PromoCampaignDetail extends Omit<PromoCampaignSummary, 'packs'> {
  packs: PromoPack[];
  warnings: string[];
}

export interface PromoListResponse {
  campaigns: PromoCampaignSummary[];
}

export interface PromoSyncAllResponse {
  synced: number;
  campaigns: PromoCampaignSummary[];
}

export interface PromoInput {
  name: string;
  team?: string;
  sheet_url: string;
}
