/**
 * The legacy live-scrape Tracker (`/tracker`).
 *
 * Distinct from campaign reports: figures are a trailing **7-day rolling**
 * window per KOL, snapshotted once per daily scrape, with deltas measured
 * against the previous available scrape date (not necessarily yesterday).
 */

/** `GET /api/health` → `last_run`. */
export interface ScrapeRun {
  status: string;
  run_date: string;
  posts_count: number | null;
  cost_usd: number | null;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
}

export interface HealthResponse {
  status: string;
  latest_scrape_date: string | null;
  last_run: ScrapeRun | null;
}

/** One KPI: a value plus its percentage change vs the previous scrape date. */
export interface Kpi {
  value: number;
  /** null when there is no comparable previous value (never fabricated as 0). */
  delta_pct: number | null;
}

/** The six KPI keys the summary endpoint returns. */
export interface TrackerKpis {
  total_views?: Kpi;
  total_engagement?: Kpi;
  /** A ratio in 0..1, NOT a percentage — multiply by 100 to display. */
  avg_engagement_rate?: Kpi;
  total_posts?: Kpi;
  active_kols?: Kpi;
  total_followers?: Kpi;
}

/** Per-KOL row in the summary. All metrics are 7-day rolling totals. */
export interface TrackerKol {
  username: string;
  display: string;
  group: string;
  followers: number;
  posts_7d: number;
  views_7d: number;
  likes_7d: number;
  comments_7d: number;
  shares_7d: number;
  saves_7d: number;
  /** Ratio in 0..1, or null when it could not be computed. */
  engagement_rate: number | null;
  delta_views_pct: number | null;
}

export interface SummaryResponse {
  /** null when the database holds no scrape yet. */
  date: string | null;
  previous_date?: string | null;
  available_dates: string[];
  group: string;
  kpis: TrackerKpis;
  kols: TrackerKol[];
}

export interface TrendPoint {
  date: string;
  value: number;
}

export interface TrendResponse {
  metric: string;
  group: string;
  days?: number;
  series: TrendPoint[];
}

/** Metrics the trend chart can plot. */
export const TREND_METRICS = ['views', 'engagement', 'followers'] as const;
export type TrendMetric = (typeof TREND_METRICS)[number];

/** One post in the KOL detail view. */
export interface TrackerPost {
  username: string;
  display: string;
  group: string;
  video_id: string;
  url: string | null;
  posted_at: string | null;
  is_pinned: boolean;
  is_slideshow: boolean;
  views: number;
  likes: number;
  comments: number;
  shares: number;
  saves: number;
}

export interface KolTrendPoint {
  date: string;
  followers: number;
  views_7d: number;
  likes_7d: number;
  posts_7d: number;
  engagement_rate: number | null;
}

export interface KolDetail {
  username: string;
  display: string;
  group: string;
  trend: KolTrendPoint[];
  posts: TrackerPost[];
}

/** Fixed content groups + the "All" pseudo-group, in display order. */
export const TRACKER_GROUP_FILTERS = [
  'All',
  'Fashion',
  'Food',
  'Beauty',
  'Household Items',
] as const;

/** Brand colour per tracker group. */
export const TRACKER_GROUP_COLORS: Record<string, string> = {
  Fashion: '#6366f1',
  Food: '#f59e0b',
  Beauty: '#ec4899',
  'Household Items': '#10b981',
};
