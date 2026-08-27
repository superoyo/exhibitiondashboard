import type { BulkKol } from '@kol/shared';

import { resolveHandles } from '@/features/roster/api/rosterApi';

import {
  dedupeExistingLinks,
  handleFromUrl,
  isProfileUrl,
  NONWORK_URL,
  normalizeUrl,
  platformOf,
  postIdOf,
} from './urlHelpers';

/**
 * The post-parse import pipeline, shared by the roster page's file/sheet import
 * and (later) the report page's auto-sync-on-refresh.
 *
 * Order matters and is preserved from the legacy implementation:
 *   1. resolve short links, so a channel link can be told from a post link
 *   2. strip profile/non-work links — they only NAME the KOL, never get tracked
 *   3. re-dedupe by (platform, post id), now that URLs are canonical
 *   4. backfill usernames from link handles, then drop rows still unidentified
 */

export interface PrepareResult {
  kols: BulkKol[];
  /** Rows we could not attribute to any KOL; they are skipped, not guessed. */
  dropped: number;
}

export type StatusFn = (message: string) => void;

/**
 * Links needing a network round-trip: no handle yet, or no extractable post id
 * (i.e. possibly a short link hiding its true destination).
 */
function urlsNeedingResolution(kols: BulkKol[]): string[] {
  return [
    ...new Set(
      kols.flatMap((k) =>
        (k.links ?? [])
          // Profile links with a handle are already canonical — resolving them
          // would add a slow HTTP round-trip per KOL for nothing.
          .filter((l) => !(l.handle && isProfileUrl(l.url)))
          .filter((l) => !l.handle || !postIdOf(l.platform, l.url))
          .map((l) => l.url),
      ),
    ),
  ];
}

export async function prepareImport(
  parsed: BulkKol[],
  onStatus?: StatusFn,
): Promise<PrepareResult> {
  const kols = parsed.map((k) => ({ ...k, links: [...(k.links ?? [])] }));

  const need = urlsNeedingResolution(kols);
  if (need.length) {
    onStatus?.(`กำลังตรวจลิงก์ ${need.length} รายการ (แยกลิงก์ช่อง/ลิงก์โพสต์)…`);
    try {
      const { handles, resolved } = await resolveHandles(need);
      for (const k of kols) {
        for (const link of k.links) {
          const resolvedHandle = handles[link.url];
          if (!link.handle && resolvedHandle) link.handle = resolvedHandle;
          const final = resolved[link.url];
          if (final && final !== link.url) {
            link.url = normalizeUrl(final);
            link.platform = platformOf(link.url);
            if (!link.handle) link.handle = handleFromUrl(link.url);
          }
        }
      }
    } catch {
      // Resolution is best-effort: unresolved rows simply won't gather stats.
      // Failing the whole import here would be worse than importing partial links.
    }
  }

  for (const k of kols) {
    const profileLinks = k.links.filter((l) => isProfileUrl(l.url) || NONWORK_URL.test(l.url));
    k.links = dedupeExistingLinks(
      k.links.filter((l) => !isProfileUrl(l.url) && !NONWORK_URL.test(l.url)),
    );

    if (!k.username) {
      const named = profileLinks.find((l) => l.handle || handleFromUrl(l.url));
      if (named) k.username = named.handle || handleFromUrl(named.url);
    }
  }

  for (const k of kols) {
    if (!k.username) {
      const withHandle = k.links.find((l) => l.handle);
      if (withHandle) k.username = withHandle.handle;
    }
    if (!k.display) k.display = k.username;
  }

  const usable = kols.filter((k) => k.username);
  return { kols: usable, dropped: kols.length - usable.length };
}

/** Summary numbers for the pre-import confirmation prompt. */
export function importSummary(kols: BulkKol[]) {
  return {
    kolCount: kols.length,
    linkCount: kols.reduce((sum, k) => sum + (k.links?.length ?? 0), 0),
    groups: [...new Set(kols.map((k) => k.group))],
  };
}

/**
 * The confirmation text. Spelled out here because it is the last thing standing
 * between a mistaken upload and the campaign's whole roster being replaced.
 */
export function buildImportConfirmMessage(
  kols: BulkKol[],
  dropped: number,
  skippedSheets: string[],
): string {
  const { kolCount, linkCount, groups } = importSummary(kols);
  const skip = skippedSheets.length
    ? `\nข้ามชีตที่ไม่ใช่งานโพสต์: ${skippedSheets.join(', ')}`
    : '';
  const extra = dropped ? `\n(ระบุ KOL ไม่ได้ ${dropped} แถว — จะข้าม)` : '';
  return (
    `พบ ${kolCount} KOL · ${linkCount} ลิงก์ (หลายแพลตฟอร์ม)\n` +
    `กลุ่ม: ${groups.join(', ')}${skip}${extra}\n\n` +
    '⚠️ การนำเข้าจะ "ลบรายชื่อเดิมทั้งหมด" ของแคมเปญนี้แล้วแทนที่ด้วยรายการใหม่ ยืนยันหรือไม่?'
  );
}

/** Split a links textarea (1 line = 1 link) into deduped KolLinks. */
export function parseLinksTextarea(value: string) {
  const urls = [
    ...new Set(
      value
        .split(/\n+/)
        .map((s) => s.trim())
        .filter(Boolean),
    ),
  ];
  return urls.map((url) => ({
    platform: platformOf(url),
    url,
    handle: handleFromUrl(url),
  }));
}
