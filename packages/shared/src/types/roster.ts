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
 * A roster row. Shape mirrors `_serialize()` in app/api/routes.py:175 — `url`,
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

/** `PATCH /api/roster/:kind/:id` — every field optional. */
export interface RosterPatchInput {
  display?: string;
  group?: string;
  subgroup?: string;
  active?: boolean;
  url?: string;
  links?: KolLink[];
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
}

export interface BulkRosterInput {
  kols: BulkKol[];
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
