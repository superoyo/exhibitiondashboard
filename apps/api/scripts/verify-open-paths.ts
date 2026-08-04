/**
 * Auth-allowlist parity check (MIGRATION_PLAN.md §6.4).
 *
 * Proves the Express guard makes the same allow/deny decision as the Python
 * `_needs_auth`, by asking BOTH live services and comparing. A 401 means
 * "auth required"; anything else means the path was let through.
 *
 * This matters in both directions:
 *   - too strict → public client links (/v/<token>) break for people with no account
 *   - too loose  → the API is exposed to the internet
 *
 * ⚠️ This proves the two agree — NOT that either is right. It passed for weeks
 * while /api/campaigns/summary was open in BOTH, serving every client's campaign
 * roster unauthenticated. For expectations that a shared mistake cannot satisfy,
 * see scripts/auth-allowlist-cases.json and the two checkers that read it.
 *
 * Run with both services up:
 *   PY=http://127.0.0.1:8000 EX=http://127.0.0.1:8080 tsx scripts/verify-open-paths.ts
 */
const PY = process.env.PY ?? 'http://127.0.0.1:8000';
const EX = process.env.EX ?? 'http://127.0.0.1:8080';

/** [method, path] pairs covering every branch of the allowlist. */
const CASES: Array<[string, string]> = [
  // exact-match opens
  ['GET', '/api/version'],
  ['GET', '/api/health'],
  // prefix opens
  ['GET', '/api/auth/profile'],
  ['GET', '/api/img?u=https://example.com/a.jpg'],
  ['GET', '/api/report/data?campaign=pao'],
  ['GET', '/api/report/tiein/status?campaign=pao'],
  ['GET', '/api/summary'],
  ['GET', '/api/trend'],
  ['GET', '/api/posts'],
  ['GET', '/api/kols/somebody'],
  // the GET-only campaign-metadata exception
  ['GET', '/api/campaigns/pao'],
  // ...and the same path with a mutating method must NOT be open
  ['PATCH', '/api/campaigns/pao'],
  ['DELETE', '/api/campaigns/pao'],
  // protected reads
  ['GET', '/api/campaigns'],
  ['GET', '/api/campaigns/summary'],
  ['GET', '/api/token'],
  ['GET', '/api/ai/key'],
  ['GET', '/api/ai/status'],
  ['GET', '/api/roster/report?campaign=pao'],
  ['GET', '/api/roster/report/sheet?campaign=pao'],
  ['GET', '/api/report/refresh/status?campaign=pao'],
  ['GET', '/api/report/profiles/status?campaign=pao'],
  ['GET', '/api/report/packshot?campaign=pao'],
  ['GET', '/api/sheet/fetch?url=https://example.com/a.xlsx'],
  // protected writes
  ['POST', '/api/token'],
  ['POST', '/api/report/refresh?campaign=pao'],
  ['POST', '/api/report/tiein?campaign=pao'],
  ['POST', '/api/resolve-handles'],
  ['POST', '/api/roster/report/bulk?campaign=pao'],
  ['POST', '/api/campaigns'],
  // near-misses that must stay protected
  ['GET', '/api/campaigns/pao/view-token'],
  ['POST', '/api/campaigns/pao/rename'],
  ['GET', '/api/reportdata'],
  ['GET', '/api/kols'],
];

/** True when the service demanded authentication. */
async function requiresAuth(base: string, method: string, path: string): Promise<boolean> {
  try {
    const res = await fetch(`${base}${path}`, {
      method,
      headers: method === 'POST' || method === 'PATCH' ? { 'Content-Type': 'application/json' } : {},
      body: method === 'POST' || method === 'PATCH' ? '{}' : undefined,
    });
    return res.status === 401;
  } catch {
    return false;
  }
}

async function main() {
  let mismatches = 0;

  for (const [method, path] of CASES) {
    const [py, ex] = await Promise.all([
      requiresAuth(PY, method, path),
      requiresAuth(EX, method, path),
    ]);
    const label = `${method.padEnd(6)} ${path}`;
    if (py === ex) {
      console.log(`  ${py ? 'auth' : 'OPEN'}  ${label}`);
    } else {
      mismatches++;
      console.error(
        `❌ MISMATCH ${label}\n     python requiresAuth=${String(py)}  express requiresAuth=${String(ex)}`,
      );
    }
  }

  console.log(`\nChecked ${String(CASES.length)} path/method combinations.`);
  if (mismatches > 0) {
    console.error(`❌ ${String(mismatches)} mismatch(es) — the guard is NOT at parity.`);
    process.exit(1);
  }
  console.log('✅ Express auth guard matches Python exactly.');
}

main().catch((err: unknown) => {
  console.error(err);
  process.exit(1);
});
