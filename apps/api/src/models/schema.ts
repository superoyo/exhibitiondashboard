import {
  bigint,
  boolean,
  customType,
  date,
  integer,
  numeric,
  pgTable,
  serial,
  text,
  timestamp,
  unique,
  varchar,
} from 'drizzle-orm/pg-core';

/**
 * Drizzle mirror of the EXISTING database schema.
 *
 * ⚠️ This file describes a database that Alembic already owns. The 15 revisions
 * in `migrations/` created these tables and are applied to production. Drizzle
 * is used here for QUERYING ONLY:
 *
 *   - never run `drizzle-kit push` or `generate` against this database
 *   - schema changes still go through a new Alembic revision
 *
 * A generated Drizzle migration would try to create or drop tables holding real
 * campaign data. See MIGRATION_PLAN.md §6.3.
 *
 * Column names mirror Python exactly — notably the logical "group" is stored as
 * `content_group`, because GROUP is a reserved SQL word. The API layer still
 * exposes it as `group`.
 *
 * Verified column-by-column against the live database; see the parity check in
 * `scripts/verify-schema.ts`.
 */

/** Postgres BYTEA — Drizzle has no first-class binary type. */
const bytea = customType<{ data: Buffer; driverData: Buffer }>({
  dataType: () => 'bytea',
});

/** The live-scrape roster (Tracker). */
export const kols = pgTable('kols', {
  id: serial('id').primaryKey(),
  username: varchar('username', { length: 255 }).notNull().unique(),
  display: varchar('display', { length: 255 }).notNull(),
  contentGroup: varchar('content_group', { length: 64 }).notNull(),
  active: boolean('active').notNull().default(true),
  createdAt: timestamp('created_at', { withTimezone: true, mode: 'string' }).defaultNow(),
});

/** Per-campaign report roster. */
export const reportKols = pgTable(
  'report_kols',
  {
    id: serial('id').primaryKey(),
    username: varchar('username', { length: 255 }).notNull(),
    display: varchar('display', { length: 255 }).notNull(),
    contentGroup: varchar('content_group', { length: 64 }).notNull(),
    subgroup: varchar('subgroup', { length: 64 }),
    campaign: varchar('campaign', { length: 32 }).notNull().default('pao'),
    url: text('url'),
    /** JSON array of {platform,url,handle}; falls back to `url` when null. */
    linksJson: text('links_json'),
    avatarUrl: text('avatar_url'),
    followers: bigint('followers', { mode: 'number' }).notNull().default(0),
    active: boolean('active').notNull().default(true),
    /** Preserves the imported file's row order. */
    sortOrder: integer('sort_order').notNull().default(0),
    createdAt: timestamp('created_at', { withTimezone: true, mode: 'string' }).defaultNow(),
  },
  (t) => [unique('uq_report_kols_campaign_username').on(t.campaign, t.username)],
);

/** Latest scraped post per video for the report roster. */
export const reportPosts = pgTable('report_posts', {
  id: serial('id').primaryKey(),
  campaign: varchar('campaign', { length: 32 }).notNull().default('pao'),
  username: varchar('username', { length: 255 }).notNull(),
  platform: varchar('platform', { length: 16 }).notNull().default('tiktok'),
  videoId: varchar('video_id', { length: 64 }).notNull().unique(),
  url: text('url'),
  coverUrl: text('cover_url'),
  avatarUrl: text('avatar_url'),
  caption: text('caption'),
  /** image_cache hash of the AI-picked product tie-in frame. */
  tieinHash: varchar('tiein_hash', { length: 64 }),
  postedAt: timestamp('posted_at', { withTimezone: true, mode: 'string' }),
  views: bigint('views', { mode: 'number' }).default(0),
  likes: bigint('likes', { mode: 'number' }).default(0),
  comments: bigint('comments', { mode: 'number' }).default(0),
  shares: bigint('shares', { mode: 'number' }).default(0),
  saves: bigint('saves', { mode: 'number' }).default(0),
  scrapedAt: timestamp('scraped_at', { withTimezone: true, mode: 'string' }).defaultNow(),
});

/** Campaign metadata. `key` is referenced by report_kols/report_posts.campaign. */
export const campaigns = pgTable('campaigns', {
  key: varchar('key', { length: 32 }).primaryKey(),
  name: varchar('name', { length: 255 }).notNull(),
  /** Random token for the public client link (/v/<token>). */
  viewToken: varchar('view_token', { length: 64 }),
  createdBy: varchar('created_by', { length: 255 }),
  createdByPhoto: text('created_by_photo'),
  emoji: varchar('emoji', { length: 8 }).notNull().default('📊'),
  subtitle: text('subtitle'),
  groupsJson: text('groups_json'),
  subgroupsJson: text('subgroups_json'),
  active: boolean('active').notNull().default(true),
  createdAt: timestamp('created_at', { withTimezone: true, mode: 'string' }).defaultNow(),
});

/** Cached remote image bytes — TikTok CDN URLs expire, so we keep our own copy. */
export const imageCache = pgTable('image_cache', {
  hash: varchar('hash', { length: 64 }).primaryKey(),
  contentType: varchar('content_type', { length: 64 }),
  data: bytea('data').notNull(),
  createdAt: timestamp('created_at', { withTimezone: true, mode: 'string' }).defaultNow(),
});

/** Runtime-editable settings (Apify token, Claude key, per-campaign cost). */
export const appSettings = pgTable('app_settings', {
  key: varchar('key', { length: 64 }).primaryKey(),
  value: text('value'),
  updatedAt: timestamp('updated_at', { withTimezone: true, mode: 'string' }).defaultNow(),
});

/** One row per scrape attempt — audit trail. */
export const scrapeRuns = pgTable('scrape_runs', {
  id: serial('id').primaryKey(),
  runDate: date('run_date').notNull(),
  apifyRunId: varchar('apify_run_id', { length: 64 }),
  /** running | success | failed */
  status: varchar('status', { length: 32 }).notNull(),
  postsCount: integer('posts_count').notNull().default(0),
  costUsd: numeric('cost_usd', { precision: 10, scale: 4 }),
  startedAt: timestamp('started_at', { withTimezone: true, mode: 'string' }).defaultNow(),
  finishedAt: timestamp('finished_at', { withTimezone: true, mode: 'string' }),
  error: text('error'),
});

/** One row per TikTok video on the live tracker. */
export const posts = pgTable('posts', {
  id: serial('id').primaryKey(),
  kolId: integer('kol_id')
    .notNull()
    .references(() => kols.id),
  videoId: varchar('video_id', { length: 64 }).notNull().unique(),
  url: text('url'),
  postedAt: timestamp('posted_at', { withTimezone: true, mode: 'string' }),
  isPinned: boolean('is_pinned').default(false),
  isSlideshow: boolean('is_slideshow').default(false),
  firstSeen: date('first_seen').notNull(),
  lastScraped: date('last_scraped').notNull(),
});

/** Metric snapshot of a post at a given scrape_date. */
export const postMetrics = pgTable(
  'post_metrics',
  {
    id: serial('id').primaryKey(),
    postId: integer('post_id')
      .notNull()
      .references(() => posts.id),
    scrapeDate: date('scrape_date').notNull(),
    views: bigint('views', { mode: 'number' }).default(0),
    likes: bigint('likes', { mode: 'number' }).default(0),
    comments: bigint('comments', { mode: 'number' }).default(0),
    shares: bigint('shares', { mode: 'number' }).default(0),
    saves: bigint('saves', { mode: 'number' }).default(0),
  },
  (t) => [unique('uq_post_metric_day').on(t.postId, t.scrapeDate)],
);

/** Per-KOL per-day rollup of the trailing 7-day window. */
export const kolDaily = pgTable(
  'kol_daily',
  {
    id: serial('id').primaryKey(),
    kolId: integer('kol_id')
      .notNull()
      .references(() => kols.id),
    scrapeDate: date('scrape_date').notNull(),
    followers: bigint('followers', { mode: 'number' }).default(0),
    posts7d: integer('posts_7d').default(0),
    views7d: bigint('views_7d', { mode: 'number' }).default(0),
    likes7d: bigint('likes_7d', { mode: 'number' }).default(0),
    comments7d: bigint('comments_7d', { mode: 'number' }).default(0),
    shares7d: bigint('shares_7d', { mode: 'number' }).default(0),
    saves7d: bigint('saves_7d', { mode: 'number' }).default(0),
    engagementRate: numeric('engagement_rate', { precision: 8, scale: 5 }),
  },
  (t) => [unique('uq_kol_daily_day').on(t.kolId, t.scrapeDate)],
);
