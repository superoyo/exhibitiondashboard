/**
 * Runs the EXPRESS campaign mutations against the same fixture as the Python
 * reference script and dumps the resulting state as JSON, so the two can be
 * diffed.
 *
 * Mutations require auth over HTTP, so both sides are exercised at the
 * implementation level instead — same seeded rows, same inputs.
 *
 * Run:  DATABASE_URL=... tsx scripts/mutation-fixture.ts
 */
import { eq, inArray } from 'drizzle-orm';

import { db, pool } from '../src/config/database.js';
import { appSettings, campaigns, reportKols, reportPosts } from '../src/models/schema.js';
import * as write from '../src/services/campaign/campaignWrite.service.js';
import { pyJsonList } from '../src/utils/pythonJson.js';

const PREFIX = 'mutex';
const KEYS = [
  `${PREFIX}-patch`,
  `${PREFIX}-arch`,
  `${PREFIX}-tok`,
  `${PREFIX}-ren`,
  `${PREFIX}-taken`,
];
const ALL = [...KEYS, `${PREFIX}-renamed`];
const SETTING_PREFIXES = ['refresh_cost:', 'sheet_url:'] as const;

async function wipe() {
  await db.delete(reportPosts).where(inArray(reportPosts.campaign, ALL));
  await db.delete(reportKols).where(inArray(reportKols.campaign, ALL));
  await db.delete(campaigns).where(inArray(campaigns.key, ALL));
  await db.delete(appSettings).where(
    inArray(
      appSettings.key,
      ALL.flatMap((k) => SETTING_PREFIXES.map((p) => `${p}${k}`)),
    ),
  );
}

async function seed(key: string, viewToken: string | null) {
  await db.insert(campaigns).values({
    key,
    name: `Name ${key}`,
    viewToken,
    emoji: '🧪',
    subtitle: 'sub',
    // Python writes json.dumps(list) which puts a space after the comma.
    groupsJson: pyJsonList(['A', 'B']),
    subgroupsJson: pyJsonList(['x']),
    active: true,
  });
  await db.insert(reportKols).values({
    username: `u_${key}`,
    display: 'U',
    contentGroup: 'A',
    campaign: key,
    followers: 10,
    active: true,
    sortOrder: 0,
  });
  await db
    .insert(reportPosts)
    .values({ campaign: key, username: `u_${key}`, platform: 'tiktok', videoId: `vid_${key}`, views: 5 });
  await db.insert(appSettings).values([
    { key: `refresh_cost:${key}`, value: '{"total":1.5,"count":2}' },
    { key: `sheet_url:${key}`, value: 'https://example.com/s.xlsx' },
  ]);
}

async function rowState(key: string) {
  const c = (await db.select().from(campaigns).where(eq(campaigns.key, key)).limit(1))[0];
  const roster = await db
    .select({ username: reportKols.username })
    .from(reportKols)
    .where(eq(reportKols.campaign, key));
  const posts = await db
    .select({ videoId: reportPosts.videoId })
    .from(reportPosts)
    .where(eq(reportPosts.campaign, key));

  const settings: Record<string, string | null> = {};
  for (const p of SETTING_PREFIXES) {
    const row = (
      await db.select().from(appSettings).where(eq(appSettings.key, `${p}${key}`)).limit(1)
    )[0];
    settings[p] = row?.value ?? null;
  }

  return {
    campaign: c
      ? {
          key: c.key,
          name: c.name,
          emoji: c.emoji,
          subtitle: c.subtitle,
          groups_json: c.groupsJson,
          subgroups_json: c.subgroupsJson,
          active: c.active,
          view_token_len: (c.viewToken ?? '').length,
        }
      : null,
    roster: roster.map((r) => r.username),
    posts: posts.map((p) => p.videoId),
    settings,
  };
}

/** Strip the fixture prefix so the two runs are comparable. */
function normalise(value: unknown): unknown {
  return JSON.parse(JSON.stringify(value).replaceAll(PREFIX, 'FIX')) as unknown;
}

async function capture(label: string, fn: () => Promise<unknown>) {
  try {
    return { [label]: await fn() };
  } catch (err) {
    const e = err as { status?: number; message?: string };
    return { [label]: { status: e.status ?? null, detail: e.message ?? String(err) } };
  }
}

async function main() {
  await wipe();
  for (const key of KEYS) {
    await seed(key, key.endsWith('-tok') ? 'preset-token' : null);
  }

  const out: Record<string, unknown> = {};

  Object.assign(
    out,
    await capture('patch', () =>
      write.patchCampaign(`${PREFIX}-patch`, {
        name: '  New Name  ',
        emoji: '🎯🎯🎯🎯🎯🎯',
        subtitle: '   ',
        groups: ['C'],
        active: false,
      }),
    ),
  );
  out.patch_state = await rowState(`${PREFIX}-patch`);

  Object.assign(out, await capture('archive', () => write.archiveCampaign(`${PREFIX}-arch`)));
  out.archive_state = await rowState(`${PREFIX}-arch`);

  Object.assign(out, await capture('token_existing', () => write.getViewToken(`${PREFIX}-tok`)));
  out.token_generated_len = (await write.getViewToken(`${PREFIX}-patch`)).token.length;

  Object.assign(
    out,
    await capture('rename', () => write.renameCampaign(`${PREFIX}-ren`, `${PREFIX}-renamed`)),
  );
  out.rename_state_new = await rowState(`${PREFIX}-renamed`);
  out.rename_state_old = await rowState(`${PREFIX}-ren`);

  Object.assign(
    out,
    await capture('rename_unchanged', () =>
      write.renameCampaign(`${PREFIX}-taken`, `${PREFIX}-taken`),
    ),
  );
  Object.assign(out, await capture('rename_bad', () => write.renameCampaign(`${PREFIX}-taken`, '!')));
  Object.assign(
    out,
    await capture('rename_conflict', () =>
      write.renameCampaign(`${PREFIX}-taken`, `${PREFIX}-renamed`),
    ),
  );

  // created_at is generated at seed time and will never match across runs.
  const sorted = Object.fromEntries(
    Object.entries(normalise(out) as Record<string, unknown>).sort(([a], [b]) =>
      a > b ? 1 : a < b ? -1 : 0,
    ),
  );
  console.log(JSON.stringify(sorted, null, 1));
  await pool.end();
}

main().catch((err: unknown) => {
  console.error(err);
  process.exit(1);
});
