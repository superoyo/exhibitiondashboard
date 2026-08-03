import { createProxyMiddleware } from 'http-proxy-middleware';
import type { RequestHandler } from 'express';

import { env } from '../config/env.js';
import { logger } from '../config/logger.js';
import { AppError } from '../utils/AppError.js';

/**
 * Migration scaffolding: forward anything Express has not ported to the Python
 * service, so the API stays complete while endpoints move over one group at a
 * time.
 *
 * Under Option B this never fully disappears — PPTX generation and the AI
 * tie-in job stay Python, because `python-pptx` reads a real .pptx template and
 * `pptxgenjs` cannot. At the end of the migration this proxy should route only
 * those, and PYTHON_SERVICE_URL becomes the sidecar's address.
 */
export function pythonProxy(): RequestHandler {
  if (!env.PYTHON_SERVICE_URL) {
    // No sidecar configured: an unported endpoint is a clear 501 rather than a
    // confusing 404 that looks like a typo.
    return (req, _res, next) => {
      next(
        new AppError(
          501,
          `endpoint ยังไม่ได้ย้ายมา Express และไม่ได้ตั้ง PYTHON_SERVICE_URL: ${req.method} ${req.path}`,
          false,
        ),
      );
    };
  }

  logger.info({ target: env.PYTHON_SERVICE_URL }, 'Proxying unported endpoints to Python');

  return createProxyMiddleware({
    target: env.PYTHON_SERVICE_URL,
    changeOrigin: true,
    /**
     * Restore the mount prefix.
     *
     * Express strips '/api' from req.url inside `app.use('/api', ...)`, so
     * without this the proxy forwards '/auth/profile' instead of
     * '/api/auth/profile'. Python has no such route, so its SPA catch-all
     * answers with the HTML shell — i.e. every proxied endpoint returns a page
     * instead of JSON. Caught by scripts/verify-open-paths.ts.
     */
    pathRewrite: (path) => `/api${path}`,
    // Long-running jobs (refresh, tie-in, PPTX build) legitimately take minutes.
    proxyTimeout: 300_000,
    timeout: 300_000,
    on: {
      error: (err, req, res) => {
        logger.error({ err, url: req.url }, 'Python proxy error');
        if ('writeHead' in res && !res.headersSent) {
          res.writeHead(502, { 'Content-Type': 'application/json; charset=utf-8' });
          res.end(JSON.stringify({ detail: 'ต่อกับบริการเบื้องหลังไม่ได้' }));
        }
      },
    },
  });
}
