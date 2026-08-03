import express from 'express';
import helmet from 'helmet';
// Named import: pino-http is CJS, so its default export is not callable under
// NodeNext module resolution.
import { pinoHttp } from 'pino-http';

import { env } from './config/env.js';
import { logger } from './config/logger.js';
import { authGuard } from './middleware/auth.middleware.js';
import { errorHandler, notFoundHandler } from './middleware/errorHandler.middleware.js';
import { pythonProxy } from './middleware/pythonProxy.js';
import { v1Router } from './routes/v1/index.js';

export function createApp() {
  const app = express();

  // Behind Railway's proxy, so req.ip / protocol come from X-Forwarded-*.
  app.set('trust proxy', 1);

  app.use(
    helmet({
      // The SPA is served from this same origin and loads Google Fonts plus the
      // host app's global-menu script, so a default CSP would break it. CSP is
      // worth adding deliberately later, not as an untested side effect here.
      contentSecurityPolicy: false,
      crossOriginEmbedderPolicy: false,
    }),
  );

  app.use(pinoHttp({ logger }));

  // JSON bodies. The limit accommodates the pack-shot upload, which arrives as a
  // base64 data URI and is capped at 8 MB of decoded image on the write path.
  app.use(express.json({ limit: '12mb' }));

  const proxy = pythonProxy();

  // ---- API ----------------------------------------------------------------
  // The guard runs before any handler so a newly-ported endpoint cannot
  // accidentally be reachable without auth, and so proxied endpoints are gated
  // here rather than relying on the Python app's own middleware.
  app.use('/api', authGuard);

  // Versioned path plus the unversioned alias the current frontend calls. Both
  // resolve to the same router; the alias is dropped once nothing uses it.
  app.use('/api/v1', v1Router);
  app.use('/api', v1Router);

  // Anything not ported yet goes to Python. Declared last so native wins.
  app.use('/api', proxy);

  // An /api path that matched nothing and had no proxy configured.
  app.use('/api', notFoundHandler);

  app.use(errorHandler);

  return app;
}

export { env };
