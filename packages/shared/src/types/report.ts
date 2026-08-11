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

// ---- Background jobs -------------------------------------------------------

/** `GET /api/jobs/active` — one entry per running or just-finished job. */
export interface ActiveJob {
  key: string;
  campaign: string;
  campaign_name: string;
  emoji: string;
  kind: 'refresh' | 'profiles' | 'tiein' | 'comments';
  kind_label: string;
  status: JobStatus;
  message: string;
  started_at: string | null;
  finished_at: string | null;
  done: number;
  /** 0 when the denominator is not known yet — the UI then shows a count with
   *  no progress bar rather than inventing a percentage. */
  total: number;
  cost_usd: number | null;
}

// ---- Comment breakdown -----------------------------------------------------

/**
 * Comment classification, mirroring app/comments.py. Three axes:
 *  - `category` is a fixed set, so the donut can be compared across campaigns
 *  - `sentiment` is only set on comments that touch the product — a comment
 *    praising the creator is not praise for the product
 *  - `theme` is free text taken from what the comments say (รสชาติ, ราคา,
 *    หาซื้อยาก), which is where product-specific detail lives without needing
 *    a different category set per campaign
 */
export type CommentCategory =
  | 'FAN'
  | 'PRODUCT'
  | 'INTENT'
  | 'ECHO'
  | 'NEG'
  | 'QUESTION'
  | 'SPAM';

export type CommentSentiment = 'pos' | 'neu' | 'neg';

export interface CommentCategoryCount {
  code: CommentCategory;
  label: string;
  count: number;
  pct: number;
}

export interface CommentPreviewItem {
  id: number;
  text: string;
  author: string | null;
  platform: string;
  /** Whose post it sits under — the card shows this, not just the commenter. */
  kol: string;
  /** Link to the post the comment was written under. Resolved at read time from
   *  the posts table, so it works for comments stored before this existed.
   *  Null when the post row is gone (roster edited after the scrape). */
  post_url: string | null;
  category: CommentCategory | null;
  label: string | null;
  sentiment: CommentSentiment | null;
  theme: string | null;
  likes: number;
  posted_at: string | null;
}

/** `GET /api/report/comments` */
export interface CommentSummary {
  total: number;
  /** Scraped but not yet classified — shown rather than hidden, so the
   *  percentages are never quietly computed over a subset. */
  unclassified: number;
  /** How many of the total are replies rather than top-level comments. */
  replies: number;
  /** Replies a KOL wrote under their own post. Counted in `total` but excluded
   *  from product sentiment and the preview — a creator answering "อร่อยจริง ๆ"
   *  is advertising, not audience voice. */
  creator_replies: number;
  by_platform: Record<string, number>;
  categories: CommentCategoryCount[];
  product_sentiment: Partial<Record<CommentSentiment, number>>;
  themes: { theme: string; count: number }[];
}

/** `GET /api/report/comments/list` */
export interface CommentListResponse {
  total: number;
  offset: number;
  limit: number;
  items: CommentPreviewItem[];
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
