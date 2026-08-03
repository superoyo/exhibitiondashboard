import * as repo from '../../repositories/roster.repo.js';
import type { ReportKolRow, TrackerKolRow } from '../../repositories/roster.repo.js';
import { getSetting, setSetting } from '../settings/appSettings.service.js';
import { AppError } from '../../utils/AppError.js';
import { kolLinks } from '../links/linkUtils.js';
import { pyJsonDumps } from '../../utils/pythonJson.js';

export type RosterKind = 'tracker' | 'report';

/**
 * Serialised roster row.
 *
 * ⚠️ KEY ORDER IS PART OF THE CONTRACT. Python builds this dict in a fixed
 * order and only appends `url` / `links` / `subgroup` when the model has those
 * columns — i.e. for `report` but not `tracker`. JSON.stringify preserves
 * insertion order, so the object is assembled in exactly that sequence to keep
 * responses byte-identical.
 */
function serializeTracker(row: TrackerKolRow) {
  return {
    id: row.id,
    username: row.username,
    display: row.display,
    group: row.contentGroup,
    active: row.active,
  };
}

function serializeReport(row: ReportKolRow) {
  return {
    id: row.id,
    username: row.username,
    display: row.display,
    group: row.contentGroup,
    active: row.active,
    url: row.url,
    links: kolLinks(row),
    subgroup: row.subgroup,
  };
}

export async function listRoster(kind: RosterKind, campaign: string) {
  if (kind === 'tracker') {
    return (await repo.listTracker()).map(serializeTracker);
  }
  return (await repo.listReport(campaign)).map(serializeReport);
}

export interface RosterAddInput {
  username: string;
  display?: string | null;
  group: string;
  subgroup?: string | null;
  url?: string | null;
}

/** Normalise a submitted username: strip, drop a leading '@', lowercase. */
function normaliseUsername(raw: string): string {
  return (raw || '').trim().replace(/^@+/, '').toLowerCase();
}

export async function addRosterKol(kind: RosterKind, campaign: string, input: RosterAddInput) {
  const username = normaliseUsername(input.username);
  if (!username) throw AppError.badRequest('username ห้ามว่าง');

  const display = (input.display || username).trim();
  const contentGroup = input.group.trim();

  if (kind === 'tracker') {
    if (await repo.findTrackerByUsername(username)) {
      throw AppError.conflict(`มี @${username} อยู่แล้ว`);
    }
    try {
      return serializeTracker(await repo.insertTracker({ username, display, contentGroup }));
    } catch {
      // A concurrent add can win the race past the check above; the unique
      // constraint then fires and this must be a 409, not a 500.
      throw AppError.conflict(`มี @${username} อยู่แล้ว`);
    }
  }

  if (await repo.findReportByUsername(campaign, username)) {
    throw AppError.conflict(`มี @${username} อยู่แล้ว`);
  }
  try {
    const row = await repo.insertReport({
      username,
      display,
      contentGroup,
      campaign,
      sortOrder: await repo.nextSortOrder(campaign),
      // Only set when the field was actually supplied, matching Python's
      // `if body.subgroup is not None` / `if body.url` guards.
      ...(input.subgroup !== undefined && input.subgroup !== null
        ? { subgroup: input.subgroup.trim() || null }
        : {}),
      ...(input.url ? { url: input.url.trim() } : {}),
    });
    return serializeReport(row);
  } catch {
    throw AppError.conflict(`มี @${username} อยู่แล้ว`);
  }
}

export interface RosterPatchInput {
  display?: string;
  group?: string;
  subgroup?: string;
  active?: boolean;
  url?: string;
  links?: Array<{ platform?: string | null; url?: string | null; handle?: string | null }>;
}

export async function patchRosterKol(kind: RosterKind, id: number, input: RosterPatchInput) {
  if (kind === 'tracker') {
    if (!(await repo.getTracker(id))) throw AppError.notFound('ไม่พบ KOL');
    const patch: Parameters<typeof repo.updateTracker>[1] = {};
    if (input.display !== undefined) patch.display = input.display.trim();
    if (input.group !== undefined) patch.contentGroup = input.group.trim();
    if (input.active !== undefined) patch.active = input.active;
    const updated = await repo.updateTracker(id, patch);
    if (!updated) throw AppError.notFound('ไม่พบ KOL');
    return serializeTracker(updated);
  }

  if (!(await repo.getReport(id))) throw AppError.notFound('ไม่พบ KOL');

  const patch: Parameters<typeof repo.updateReport>[1] = {};
  if (input.display !== undefined) patch.display = input.display.trim();
  if (input.group !== undefined) patch.contentGroup = input.group.trim();
  if (input.active !== undefined) patch.active = input.active;
  if (input.subgroup !== undefined) patch.subgroup = input.subgroup.trim() || null;

  if (input.links !== undefined) {
    // Drop entries with no URL, then keep platform/url/handle only.
    const links = input.links
      .filter((l) => (l.url ?? '').trim())
      .map((l) => ({
        platform: l.platform ?? '',
        url: (l.url ?? '').trim(),
        handle: l.handle ?? '',
      }));
    patch.linksJson = links.length ? pyJsonDumps(links) : null;
    // `url` stays the primary link so pre-multiplatform readers still work.
    patch.url = links.length ? (links[0]?.url ?? null) : null;
  } else if (input.url !== undefined) {
    // `links` wins over `url` when both are sent — same precedence as Python.
    patch.url = input.url.trim();
  }

  const updated = await repo.updateReport(id, patch);
  if (!updated) throw AppError.notFound('ไม่พบ KOL');
  return serializeReport(updated);
}

export async function deleteRosterKol(kind: RosterKind, id: number) {
  const removed = kind === 'tracker' ? await repo.deleteTracker(id) : await repo.deleteReport(id);
  if (!removed) throw AppError.notFound('ไม่พบ KOL');
  return { status: 'deleted' as const, id };
}

// ---- bulk replace ---------------------------------------------------------

export interface BulkKolInput {
  username: string;
  display?: string | null;
  group?: string | null;
  subgroup?: string | null;
  url?: string | null;
  links?: Array<{ platform?: string | null; url: string; handle?: string | null }> | null;
  followers?: number | null;
}

/**
 * Replace a campaign's entire roster from a parsed sheet.
 *
 * Rows sharing a username are MERGED (see below) — this replaced an earlier
 * last-wins rule in 24628c9, because last-wins silently dropped the links of
 * every row but the last. `report_posts` are intentionally left alone; the next
 * Refresh re-matches them.
 */
export async function bulkReplaceRoster(
  campaign: string,
  kolsIn: BulkKolInput[],
  sheetUrl: string | null | undefined,
): Promise<{ status: 'replaced'; count: number }> {
  // Same account on several rows (a page that posted more than once) is MERGED,
  // not last-wins: the first row keeps name/group/order and the links are
  // concatenated, so a second row can no longer silently discard the first row's
  // links. Followers are backfilled only when the first row had none.
  const seen = new Map<string, BulkKolInput>();
  for (const k of kolsIn) {
    const username = normaliseUsername(k.username);
    if (!username) continue;

    const prev = seen.get(username);
    if (prev) {
      prev.links = [...(prev.links ?? []), ...(k.links ?? [])];
      if (!prev.followers && k.followers) prev.followers = k.followers;
    } else {
      // Copy, so merging never mutates the caller's array.
      seen.set(username, { ...k, links: [...(k.links ?? [])] });
    }
  }
  if (!seen.size) throw AppError.badRequest('ไม่พบรายชื่อ KOL ที่ใช้ได้ในไฟล์/ชีต');

  const rows = [...seen.entries()].map(([username, k], index) => {
    // Merging rows can bring the same post in twice, so dedupe by
    // (platform, url-without-query) — the same key the sheet importer uses.
    const links: Array<{ platform: string; url: string; handle: string }> = [];
    const dedup = new Set<string>();
    for (const l of k.links ?? []) {
      if (!l.url || !l.url.trim()) continue;
      const url = l.url.trim();
      const key = `${l.platform ?? ''} ${(url.split('?')[0] ?? '').replace(/\/+$/, '').toLowerCase()}`;
      if (dedup.has(key)) continue;
      dedup.add(key);
      links.push({ platform: l.platform ?? '', url, handle: l.handle ?? '' });
    }
    const primary = (k.url ? k.url.trim() : '') || links[0]?.url || '';

    return {
      // sort_order preserves the source file's row order.
      sortOrder: index,
      username,
      display: (k.display || username).trim(),
      contentGroup: (k.group || 'KOL').trim() || 'KOL',
      subgroup: (k.subgroup ? k.subgroup.trim() : null) || null,
      url: primary || null,
      linksJson: links.length ? pyJsonDumps(links) : null,
      followers: Math.trunc(Number(k.followers ?? 0)) || 0,
    };
  });

  const count = await repo.replaceReportRoster(campaign, rows);

  // Remember the source file so the campaign can be re-synced later. Note the
  // `!== undefined` check: an empty string deliberately CLEARS the link.
  if (sheetUrl !== undefined && sheetUrl !== null) {
    await setSetting(`sheet_url:${campaign}`, sheetUrl.trim());
  }
  return { status: 'replaced', count };
}

/** The online file this campaign was last imported from, or '' if none. */
export async function getSheetUrl(campaign: string): Promise<{ url: string }> {
  return { url: (await getSetting(`sheet_url:${campaign}`)) ?? '' };
}
