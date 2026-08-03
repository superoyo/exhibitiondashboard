/**
 * EXPRESS roster fixture — mirror of the Python reference script.
 *
 * Roster endpoints are auth-protected, so comparing them over HTTP only ever
 * compares two 401s. Both implementations are therefore driven directly against
 * identically-seeded rows, and the raw JSON is diffed — key ORDER included,
 * since it is part of the response contract.
 *
 * Run:  DATABASE_URL=... tsx scripts/roster-fixture.ts
 */
import { and, eq, like } from 'drizzle-orm';

import { db, pool } from '../src/config/database.js';
import { appSettings, campaigns, kols, reportKols, reportPosts } from '../src/models/schema.js';
import * as service from '../src/services/roster/roster.service.js';

const C = 'rosex';
const TRACK_USERS = ['zz_rosex_b', 'zz_rosex_a'];

const LINKS = [
  { platform: 'tiktok', url: 'https://www.tiktok.com/@one/video/7311111111111111111', handle: 'one' },
  {
    platform: 'tiktok',
    url: 'https://www.tiktok.com/@one/video/7311111111111111111?is_from_webapp=1',
    handle: 'one',
  },
  { platform: 'facebook', url: 'https://www.facebook.com/one/posts/12345', handle: '', followers: '4200' },
  { platform: '', url: '  ', handle: 'x' },
  { platform: null, url: 'https://example.com/advertorial', handle: null },
];

async function seed() {
  await db.delete(reportPosts).where(eq(reportPosts.campaign, C));
  await db.delete(reportKols).where(eq(reportKols.campaign, C));
  await db.delete(campaigns).where(eq(campaigns.key, C));
  await db.delete(appSettings).where(eq(appSettings.key, `sheet_url:${C}`));
  // The tracker roster is GLOBAL, so clear every fixture prefix or the Python
  // and Express runs pollute each other's list output.
  await db.delete(kols).where(like(kols.username, 'zz_ros%'));

  await db.insert(campaigns).values({ key: C, name: 'Roster Fix', emoji: '🧪', active: true });
  await db.insert(reportKols).values([
    {
      username: 'one', display: 'One', contentGroup: 'Big', subgroup: 'Sub', campaign: C,
      url: 'https://old.example.com/x', linksJson: JSON.stringify(LINKS),
      followers: 100, active: true, sortOrder: 2,
    },
    {
      username: 'two', display: 'Two', contentGroup: 'Big', subgroup: null, campaign: C,
      url: 'https://www.instagram.com/p/AbCdEfGhIjK/', linksJson: null,
      followers: 0, active: false, sortOrder: 1,
    },
    {
      username: 'three', display: 'Three', contentGroup: 'Other', subgroup: '', campaign: C,
      url: null, linksJson: null, followers: 5, active: true, sortOrder: 0,
    },
  ]);
  await db.insert(kols).values(
    TRACK_USERS.map((u) => ({ username: u, display: `D ${u}`, contentGroup: 'Food', active: true })),
  );
  await db.insert(appSettings).values({ key: `sheet_url:${C}`, value: 'https://docs.google.com/x' });
}

const out: Record<string, unknown> = {};

async function cap(label: string, fn: () => Promise<unknown>) {
  try {
    out[label] = await fn();
  } catch (err) {
    const e = err as { status?: number; message?: string };
    out[label] = { status: e.status ?? null, detail: e.message ?? String(err) };
  }
}

async function main() {
  await seed();

  await cap('list_report', async () => ({ kols: await service.listRoster('report', C) }));
  await cap('list_tracker', async () => ({ kols: await service.listRoster('tracker', C) }));
  await cap('sheet', () => service.getSheetUrl(C));

  await cap('add_report', () =>
    service.addRosterKol('report', C, {
      username: '  @NEWguy ', display: '  ', group: ' G ', subgroup: ' S ', url: ' https://tt.com/a ',
    }),
  );
  await cap('add_report_dup', () =>
    service.addRosterKol('report', C, { username: 'one', group: 'G' }),
  );
  await cap('add_report_blank', () =>
    service.addRosterKol('report', C, { username: '  @  ', group: 'G' }),
  );
  await cap('add_tracker', () =>
    service.addRosterKol('tracker', C, { username: 'ZZ_Rosex_New', group: 'Beauty' }),
  );

  const rid = (
    await db
      .select({ id: reportKols.id })
      .from(reportKols)
      .where(and(eq(reportKols.campaign, C), eq(reportKols.username, 'three')))
      .limit(1)
  )[0]?.id;
  const tid = (
    await db.select({ id: kols.id }).from(kols).where(eq(kols.username, TRACK_USERS[0]!)).limit(1)
  )[0]?.id;
  if (rid === undefined || tid === undefined) throw new Error('fixture ids missing');

  await cap('patch_report_links', () =>
    service.patchRosterKol('report', rid, {
      display: ' P ', group: ' NG ', active: false, subgroup: '  ',
      links: [
        { platform: 'tiktok', url: ' https://www.tiktok.com/@p/video/7322222222222222222 ', handle: 'p' },
        { platform: null, url: '', handle: 'drop' },
      ],
    }),
  );
  await cap('patch_report_clearlinks', () =>
    service.patchRosterKol('report', rid, { links: [] }),
  );
  await cap('patch_tracker', () =>
    service.patchRosterKol('tracker', tid, {
      display: ' T ', group: ' Fashion ', active: false, subgroup: 'ignored', url: 'ignored',
    }),
  );
  await cap('patch_missing', () =>
    service.patchRosterKol('report', 99999999, { display: 'x' }),
  );
  await cap('del_report', () => service.deleteRosterKol('report', rid));
  await cap('del_missing', () => service.deleteRosterKol('report', rid));

  await cap('bulk', () =>
    service.bulkReplaceRoster(
      C,
      [
        { username: '@DupUser', display: 'First', group: 'A', links: [{ url: 'https://a.com/1' }] },
        {
          username: 'dupuser', display: 'Second', group: ' ', subgroup: ' S ', followers: 77,
          links: [
            { platform: 'tiktok', url: ' https://b.com/2 ', handle: 'h' },
            { url: '  ' },
          ],
        },
        { username: '', group: 'A' },
        { username: 'solo', url: ' https://c.com/3 ' },
      ],
      '  https://new.example.com/s  ',
    ),
  );
  await cap('list_after_bulk', async () => ({ kols: await service.listRoster('report', C) }));
  await cap('sheet_after_bulk', () => service.getSheetUrl(C));
  await cap('bulk_empty', () => service.bulkReplaceRoster(C, [], undefined));

  console.log(JSON.stringify(out, null, 1));
  await pool.end();
}

main().catch((err: unknown) => {
  console.error(err);
  process.exit(1);
});
