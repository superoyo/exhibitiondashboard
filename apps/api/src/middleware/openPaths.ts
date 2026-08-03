/**
 * Which /api paths skip bearer authentication.
 *
 * ⚠️ Ported VERBATIM from `_needs_auth` in app/main.py:40. Treat this as data,
 * not code to tidy. Getting it wrong in either direction is severe:
 *
 *   - too strict → the public client links (/v/<token>) break, because the
 *     pages they render read these endpoints with no session at all
 *   - too loose  → the whole API is exposed to the internet
 *
 * `scripts/verify-open-paths.ts` checks this against the Python original.
 */

/** Open when the path STARTS WITH one of these. */
export const OPEN_API_PREFIXES = [
  '/api/auth/', // login / profile proxy
  '/api/img', // image cache (used by view-only pages)
  '/api/report/data', // report stats (used by view-only pages)
  '/api/report/tiein/status', // read-only job progress (diagnostics)
  '/api/summary',
  '/api/trend',
  '/api/posts',
  '/api/kols/',
] as const;

/** Open only on an EXACT match. `/api/scrape/run` has its own X-ADMIN-KEY gate. */
export const OPEN_API_EXACT = new Set(['/api/version', '/api/health', '/api/scrape/run']);

/**
 * Single-campaign metadata is read by view-only pages to render the title.
 * GET only — the PATCH/DELETE on the same path must stay protected.
 */
const CAMPAIGN_META_GET = /^\/api\/campaigns\/[^/]+$/;

export function needsAuth(method: string, path: string): boolean {
  if (!path.startsWith('/api/')) return false;
  if (OPEN_API_EXACT.has(path)) return false;
  if (OPEN_API_PREFIXES.some((prefix) => path.startsWith(prefix))) return false;
  if (method.toUpperCase() === 'GET' && CAMPAIGN_META_GET.test(path)) return false;
  return true;
}
