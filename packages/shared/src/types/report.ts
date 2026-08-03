import type { Platform } from './platform.js';

/**
 * One row of `GET /api/report/data` — a single KOL on a single platform, showing
 * that platform's best-performing post.
 *
 * Rows exist for EVERY active roster entry, with zeroed stats when nothing has
 * been scraped yet, so the report's structure is visible before links are added.
 * `has_data` distinguishes "genuinely zero" from "not scraped".
 */
export interface ReportRecord {
  username: string;
  /** The roster's display name. */
  nickname: string;
  platform: Platform;
  /** Server-side human label for the platform. */
  platform_label: string;
  /** Subgroup when the campaign uses two levels, else the big group. */
  category: string;
  /** Top-level group — drives the "กลุ่มใหญ่" filter. */
  biggroup: string;
  followers: number;
  views: number;
  likes: number;
  comments: number;
  shares: number;
  saves: number;
  /** ISO date (yyyy-mm-dd) or '' when unknown. */
  posted: string;
  url: string;
  thumb: string;
  avatar: string;
  has_data: boolean;
}

export interface ReportDataResponse {
  records: ReportRecord[];
  refreshed_at: string | null;
  roster_count: number;
  /** How many records actually have scraped stats. */
  post_count: number;
  kol_count: number;
  /** Accumulated Apify spend for this campaign, in USD. */
  cost_total: number;
  cost_count: number;
}

/**
 * A record with the derived engagement figures the UI needs.
 *
 * ER rules, preserved exactly from the legacy renderer:
 *  - normally engagement / views
 *  - photo posts (Facebook/Instagram) expose no view count, so fall back to
 *    engagement / followers and flag it with `erByFollowers` (rendered as `*`)
 *  - with neither basis available, `erUnavailable` is set and the UI shows an
 *    em dash — never a fabricated 0.00%
 */
export interface ReportRecordDerived extends ReportRecord {
  engagement: number;
  er: number;
  erByFollowers: boolean;
  erUnavailable: boolean;
}

/** Metric keys the podium can rank by. */
export const REPORT_METRICS = ['views', 'engagement', 'er', 'likes', 'saves'] as const;
export type ReportMetric = (typeof REPORT_METRICS)[number];

/** Sentinel used by the podium/group filters for "no filter". */
export const FILTER_ALL = 'ทั้งหมด';

/**
 * Progress of a long-running background job (`refresh`, `profiles`, `tiein`).
 * Held in the server's process memory, so it resets if the worker restarts.
 */
export type JobStatus = 'idle' | 'running' | 'success' | 'failed';

export interface JobState {
  status: JobStatus;
  message: string;
  started_at: string | null;
  finished_at: string | null;
  kol_count: number;
  /** Posts processed — the tie-in job reports newly-found shots here. */
  posts: number;
  cost_usd: number | null;
}

/** `GET /api/report/packshot` */
export interface PackshotState {
  is_set: boolean;
  /** data: URI thumbnail, present only when one is set. */
  preview?: string;
}

/** `POST /api/report/packshot` */
export interface PackshotSaveResult {
  /** Clips that previously found no tie-in and are now eligible to retry. */
  unlocked?: number;
}
