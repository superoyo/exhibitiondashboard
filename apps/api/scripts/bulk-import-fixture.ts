/**
 * EXPRESS counterpart to scripts/parity/bulk_import_reference.py.
 *
 * Same payload, same campaign shape, same dumped state — so the two outputs can
 * be diffed directly. Covers the behaviour changed by 24628c9: rows for the same
 * account are MERGED (not last-wins), links are concatenated then deduped by
 * (platform, url-without-query), and followers backfill only when the first row
 * had none.
 *
 * Run:  DATABASE_URL=... tsx scripts/bulk-import-fixture.ts
 */
import { asc, eq } from 'drizzle-orm';

import { db, pool } from '../src/config/database.js';
import { appSettings, campaigns, reportKols, reportPosts } from '../src/models/schema.js';
import * as service from '../src/services/roster/roster.service.js';
import type { BulkKolInput } from '../src/services/roster/roster.service.js';

const C = 'paritybulk';

const PAYLOAD: BulkKolInput[] = [
  {
    username: '@DupUser', display: 'First', group: 'A', subgroup: 'S1', followers: 0,
    links: [
      { platform: 'tiktok', url: 'https://a.com/1' },
      { platform: 'tiktok', url: 'https://shared.com/p?utm=1' },
    ],
  },
  {
    username: 'dupuser', display: 'Second', group: 'ZZZ', subgroup: 'S2', followers: 77,
    links: [
      { platform: 'tiktok', url: 'https://b.com/2', handle: 'h' },
      { platform: 'tiktok', url: 'https://shared.com/p/' },
      { url: '   ' },
    ],
  },
  { username: '', group: 'A', links: [{ url: 'https://ignored.com/x' }] },
  { username: 'solo', url: ' https://c.com/3 ', followers: 5 },
];

async function wipe() {
  await db.delete(reportPosts).where(eq(reportPosts.campaign, C));
  await db.delete(reportKols).where(eq(reportKols.campaign, C));
  await db.delete(campaigns).where(eq(campaigns.key, C));
  await db.delete(appSettings).where(eq(appSettings.key, `sheet_url:${C}`));
}

async function main() {
  await wipe();
  await db.insert(campaigns).values({ key: C, name: 'Parity Bulk', emoji: '🧪', active: true });

  const out: Record<string, unknown> = {};

  try {
    out.bulk = await service.bulkReplaceRoster(C, PAYLOAD, '  https://sheet.example/s  ');
  } catch (err) {
    const e = err as { status?: number; message?: string };
    out.bulk = { status: e.status ?? null, detail: e.message ?? String(err) };
  }

  const rows = await db
    .select()
    .from(reportKols)
    .where(eq(reportKols.campaign, C))
    .orderBy(asc(reportKols.sortOrder), asc(reportKols.id));
  out.rows = rows.map((r) => ({
    sort_order: r.sortOrder,
    username: r.username,
    display: r.display,
    group: r.contentGroup,
    subgroup: r.subgroup,
    url: r.url,
    links_json: r.linksJson,
    followers: r.followers,
    active: r.active,
  }));
  const setting = (
    await db.select().from(appSettings).where(eq(appSettings.key, `sheet_url:${C}`)).limit(1)
  )[0];
  out.sheet_url = setting?.value ?? null;

  try {
    out.bulk_empty = await service.bulkReplaceRoster(C, [], undefined);
  } catch (err) {
    const e = err as { status?: number; message?: string };
    out.bulk_empty = { status: e.status ?? null, detail: e.message ?? String(err) };
  }

  await wipe();
  console.log(JSON.stringify(out, null, 1));
  await pool.end();
}

main().catch((err: unknown) => {
  console.error(err);
  process.exit(1);
});
