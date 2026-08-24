import type { Platform } from './platform.js';

/**
 * Two separate rosters exist and must not be conflated:
 *  - `report`  — per-campaign roster (`report_kols`), scoped by ?campaign=,
 *                carries post links and an optional subgroup
 *  - `tracker` — the legacy live-scrape roster (`kols`), one global list with a
 *                fixed group set and no post links
 */
export type RosterKind = 'tracker' | 'report';

/** Fixed content groups for the Tracker roster (not campaign-configurable). */
export const TRACKER_GROUPS = ['Fashion', 'Food', 'Beauty', 'Household Items'] as const;

/** One channel/post link attached to a KOL. */
export interface KolLink {
  platform: Platform | '';
  url: string;
  /** The posting account's @handle, when we could determine it. */
  handle: string;
}

/**
 * The KPI unit a KOL (or a whole group) was sold on. Impressions and Reach are
 * backstage numbers — not verifiable from public data — so the UI shows those
 * targets without an achievement figure.
 */
export type KpiMetric = 'views' | 'impressions' | 'interaction' | 'reach';

/** One sold KPI. A KOL or group can carry several (Views AND Engagement). */
export interface KolKpi {
  /** Usually a KpiMetric; free text so a new sales unit is data, not a crash. */
  metric: string;
  target: number;
}

/**
 * A roster row. Shape mirrors `_serialize()` in app/api/routes.py — `url`,
 * `links` and `subgroup` are only present on models that have those columns,
 * so all three are optional.
 */
export interface RosterKol {
  id: number;
  username: string;
  display: string;
  /** Serialized from `content_group`. */
  group: string;
  active: boolean;
  url?: string | null;
  links?: KolLink[];
  subgroup?: string | null;
  /** Commercial fields (report roster only) — served ONLY by the
   *  authenticated roster endpoints, never by /api/report/data. */
  cost_thb?: number | null;
  boost_thb?: number | null;
  kpis?: KolKpi[];
}

export interface RosterListResponse {
  kols: RosterKol[];
}

/** `POST /api/roster/:kind` — `group` is required by the backend. */
export interface RosterAddInput {
  username: string;
  display?: string;
  group: string;
  subgroup?: string;
  url?: string;
}

/** `PATCH /api/roster/:kind/:id` — every field optional. For the commercial
 *  fields, -1 (numbers) or '' (metric) clears the stored value; absent leaves
 *  it alone. */
export interface RosterPatchInput {
  display?: string;
  group?: string;
  subgroup?: string;
  active?: boolean;
  url?: string;
  links?: KolLink[];
  cost_thb?: number;
  boost_thb?: number;
  /** Full replacement; [] clears. */
  kpis?: KolKpi[];
}

export interface RosterDeleteResponse {
  status: 'deleted';
  id: number;
}

// ---- Bulk import ----------------------------------------------------------

/** One parsed KOL, as produced by the workbook parser and sent to /bulk. */
export interface BulkKol {
  username: string;
  display: string;
  group: string;
  subgroup: string;
  links: KolLink[];
  followers: number;
  /** From the planner's sheet, when its columns exist. null = not stated. */
  cost_thb?: number | null;
  boost_thb?: number | null;
  kpis?: KolKpi[];
}

// ---- Group-level KPIs -------------------------------------------------------

/** `GET /api/roster/report/groupkpi` — {group_name: KPI list}. */
export interface GroupKpiResponse {
  groups: Record<string, KolKpi[]>;
}

export interface BulkRosterInput {
  kols: BulkKol[];
  /** Group-total KPIs found as vertically-merged cells in the sheet. */
  group_kpis?: { group: string; kpis: KolKpi[] }[];
  /** Remembered so the campaign can be re-synced from the same file later. */
  sheet_url?: string;
}

export interface BulkRosterResponse {
  status: 'replaced';
  count: number;
}

/** `GET /api/roster/report/sheet` — '' when no file has been linked. */
export interface SheetLinkResponse {
  url: string;
}

/**
 * `POST /api/resolve-handles` — maps each submitted URL to the posting
 * account's handle and to its canonical final URL. Short links (vt.tiktok.com,
 * FB share links) hide whether they point at a profile or a post, so the
 * resolved URL is what makes that distinction possible.
 */
export interface ResolveHandlesResponse {
  handles: Record<string, string>;
  resolved: Record<string, string>;
}
