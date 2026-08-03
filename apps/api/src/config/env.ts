import path from 'node:path';
import { z } from 'zod';

/**
 * Environment configuration, validated once at boot.
 *
 * Failing fast here is deliberate: a missing DATABASE_URL should stop the
 * process with one clear message, not surface as a connection error on the
 * first request an hour later.
 */
const schema = z.object({
  NODE_ENV: z.enum(['development', 'production', 'test']).default('development'),
  PORT: z.coerce.number().int().positive().default(8080),
  LOG_LEVEL: z.enum(['fatal', 'error', 'warn', 'info', 'debug', 'trace']).default('info'),

  DATABASE_URL: z.string().min(1, 'DATABASE_URL is required'),

  /** Identity backend. Same default as the Python app. */
  WAZZUP_BASE_URL: z.string().url().default('https://api.fareastfamelineddb.com'),

  /** Guards the manual scrape trigger (header X-ADMIN-KEY). */
  ADMIN_KEY: z.string().default(''),

  APIFY_TOKEN: z.string().default(''),

  /**
   * Migration scaffolding: anything not yet ported is proxied here. Unset once
   * the Python side only handles PPTX + AI tie-in.
   */
  PYTHON_SERVICE_URL: z.string().url().optional(),

  /**
   * Service timezone. Load-bearing: it decides the offset timestamps are
   * rendered in, and the Python app runs as Asia/Bangkok. See utils/dates.ts.
   */
  TZ: z.string().default('Asia/Bangkok'),

  /** Built React SPA, relative to the repo root. */
  WEB_DIST_DIR: z.string().default('apps/web/dist'),
});

const parsed = schema.safeParse(process.env);
if (!parsed.success) {
  const issues = parsed.error.issues.map((i) => `  - ${i.path.join('.')}: ${i.message}`);
  // The logger itself depends on this config, so stderr is all we have here.
  console.error(`Invalid environment configuration:\n${issues.join('\n')}`);
  process.exit(1);
}

/** Repo root, resolved from this file's location (apps/api/src/config). */
const REPO_ROOT = path.resolve(import.meta.dirname, '../../../..');

export const env = {
  ...parsed.data,
  isProduction: parsed.data.NODE_ENV === 'production',
  /** Absolute path to the built SPA. */
  webDistPath: path.resolve(REPO_ROOT, parsed.data.WEB_DIST_DIR),
  repoRoot: REPO_ROOT,
} as const;
