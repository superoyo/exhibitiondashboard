import { createApp } from './app.js';
import { env } from './config/env.js';
import { assertDatabaseReachable, pool } from './config/database.js';
import { logger } from './config/logger.js';
import { pruneTokenCache } from './services/auth/wazzup.service.js';

/** Hourly sweep so the token cache cannot grow without bound. */
const CACHE_PRUNE_MS = 60 * 60 * 1000;

async function main() {
  await assertDatabaseReachable();
  logger.info('Database reachable');

  const app = createApp();
  const server = app.listen(env.PORT, () => {
    logger.info({ port: env.PORT, env: env.NODE_ENV }, 'API listening');
  });

  const prune = setInterval(pruneTokenCache, CACHE_PRUNE_MS);
  prune.unref();

  /** Finish in-flight requests before exiting, so a deploy drops nothing. */
  const shutdown = (signal: string) => {
    logger.info({ signal }, 'Shutting down');
    server.close(() => {
      void pool.end().then(() => process.exit(0));
    });
    // Don't hang forever if a connection refuses to close.
    setTimeout(() => process.exit(1), 10_000).unref();
  };

  process.on('SIGTERM', () => shutdown('SIGTERM'));
  process.on('SIGINT', () => shutdown('SIGINT'));
}

main().catch((err: unknown) => {
  logger.fatal({ err }, 'Failed to start');
  process.exit(1);
});
