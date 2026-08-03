import type { RequestHandler } from 'express';

import { env } from '../config/env.js';
import { isTokenValid } from '../services/auth/wazzup.service.js';
import { AppError } from '../utils/AppError.js';
import { needsAuth } from './openPaths.js';

/** Extract a bearer token from the Authorization header, or '' if absent. */
function bearerToken(header: string | undefined): string {
  if (!header?.toLowerCase().startsWith('bearer ')) return '';
  return header.slice(7).trim();
}

/**
 * Bearer-token gate for mutating / costly / internal API calls.
 *
 * View-only client pages must keep working WITHOUT login, so the endpoints they
 * read stay open — see `openPaths.ts`, which is the authority on that list.
 */
export const authGuard: RequestHandler = (req, res, next) => {
  // MUST use originalUrl, not req.path.
  //
  // Express strips the mount prefix from `req.path` inside a mounted middleware,
  // so under `app.use('/api', authGuard)` a request to /api/token arrives with
  // req.path === '/token'. The allowlist's first test is
  // `path.startsWith('/api/')`, so every protected endpoint would fail OPEN —
  // i.e. the entire write API exposed. Caught by scripts/verify-open-paths.ts.
  //
  // originalUrl is always the full request target regardless of mounting. Only
  // the query string is removed — the path is otherwise left EXACTLY as sent,
  // because the allowlist is prefix-based and Python does no normalising either
  // (e.g. '/api/kols/' must still match the '/api/kols/' prefix).
  const path = req.originalUrl.split('?')[0] ?? '';
  if (!needsAuth(req.method, path)) {
    next();
    return;
  }

  const token = bearerToken(req.headers.authorization);
  if (!token) {
    next(AppError.unauthorized());
    return;
  }

  void isTokenValid(token)
    .then((ok) => {
      if (!ok) {
        next(AppError.unauthorized());
        return;
      }
      res.locals.token = token;
      next();
    })
    .catch(next);
};

/**
 * X-ADMIN-KEY gate for the manual scrape trigger.
 *
 * Kept separate from the bearer guard on purpose: cron and shell one-offs call
 * this endpoint without a user session.
 */
export const adminKeyGuard: RequestHandler = (req, _res, next) => {
  const provided = req.header('x-admin-key') ?? '';
  // An unset ADMIN_KEY must DENY rather than allow everyone through.
  if (!env.ADMIN_KEY || provided !== env.ADMIN_KEY) {
    next(new AppError(401, 'invalid admin key'));
    return;
  }
  next();
};
