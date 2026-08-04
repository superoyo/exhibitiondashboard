/**
 * Assert needsAuth() matches scripts/auth-allowlist-cases.json.
 *
 * Pure logic — no server needed, unlike scripts/verify-open-paths.ts. That one
 * compares the two live services against EACH OTHER, so it passes whenever both
 * are wrong the same way: /api/campaigns/summary was open in Python AND Express,
 * and the parity check stayed green while every client's campaign roster was
 * public. This checks against stated expectations instead.
 *
 * The Python counterpart reads the same file, so neither implementation can drift
 * from the expectations or from the other.
 *
 *   pnpm --filter @kol/api exec tsx scripts/check-needs-auth.ts
 */
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { needsAuth } from '../src/middleware/openPaths.js';

interface Case {
  method: string;
  path: string;
  needsAuth: boolean;
  why: string;
}

const here = dirname(fileURLToPath(import.meta.url));
const casesPath = resolve(here, '../../../scripts/auth-allowlist-cases.json');
const { cases } = JSON.parse(readFileSync(casesPath, 'utf8')) as { cases: Case[] };

let failed = 0;
for (const c of cases) {
  const got = needsAuth(c.method, c.path);
  const ok = got === c.needsAuth;
  if (!ok) failed += 1;
  const label = c.needsAuth ? 'AUTH' : 'OPEN';
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${label.padEnd(4)} ${c.method.padEnd(6)} ${c.path}`);
  if (!ok) console.log(`       expected needsAuth=${c.needsAuth}, got ${got} — ${c.why}`);
}

console.log();
if (failed > 0) {
  console.log(`FAIL: ${failed} of ${cases.length} cases wrong`);
  process.exit(1);
}
console.log(`OK: all ${cases.length} cases match`);
