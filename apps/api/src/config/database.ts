import { drizzle } from 'drizzle-orm/node-postgres';
import { Pool } from 'pg';

import * as schema from '../models/schema.js';
import { env } from './env.js';
import { logger } from './logger.js';

/**
 * Postgres pool.
 *
 * Railway's Postgres plugin and the local embedded server both accept a plain
 * connection string, including the unix-socket form `?host=/path/to/dir` that
 * `scripts/dev_db.py` writes.
 */
export const pool = new Pool({
  connectionString: env.DATABASE_URL,
  // Modest ceiling: this process shares the database with the Python service
  // during the migration, and Railway's plugin has a connection limit.
  max: 10,
  idleTimeoutMillis: 30_000,
});

pool.on('error', (err) => {
  logger.error({ err }, 'Unexpected Postgres pool error');
});

export const db = drizzle(pool, { schema });

export type Database = typeof db;

/** Verify connectivity at boot so a bad URL fails loudly and immediately. */
export async function assertDatabaseReachable(): Promise<void> {
  const client = await pool.connect();
  try {
    await client.query('SELECT 1');
  } finally {
    client.release();
  }
}
