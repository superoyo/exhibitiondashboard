import type { CommentExportResponse } from '@kol/shared';

/**
 * Comment rows → a downloaded .xlsx.
 *
 * Built in the browser with SheetJS, which the app already loads for roster
 * import, so this adds no server dependency and no temp files. It also sidesteps
 * CSV: Excel on Windows reads a UTF-8 CSV as mojibake unless it is BOM-prefixed,
 * and every comment here is Thai.
 *
 * Loaded on demand — the same reason workbook.ts does: SheetJS is ~120 kB
 * gzipped and only needed the moment someone presses Export.
 */

/** Header text, in the column order the sheet uses. */
const COLUMNS: { key: string; header: string; width: number }[] = [
  { key: 'kol', header: 'KOL', width: 20 },
  { key: 'platform', header: 'แพลตฟอร์ม', width: 12 },
  { key: 'label', header: 'ประเภท', width: 24 },
  { key: 'theme', header: 'เรื่องย่อย', width: 14 },
  { key: 'text', header: 'คอมเมนต์', width: 70 },
  { key: 'author', header: 'ผู้คอมเมนต์', width: 20 },
  { key: 'likes', header: 'ไลก์', width: 8 },
  { key: 'reply', header: 'เป็น Reply', width: 10 },
  { key: 'posted', header: 'วันที่คอมเมนต์', width: 18 },
  { key: 'post_url', header: 'ลิงก์โพสต์', width: 46 },
];

/** yyyy-mm-dd hh:mm in local time, or '' — Excel shows an ISO string as text
 *  with a T in the middle, which nobody wants to read or sort. */
function stamp(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(
    d.getMinutes(),
  )}`;
}

/**
 * The tab is named "Comments", not after the campaign: Excel forbids : \ / ? * [ ]
 * in a sheet name and caps it at 31 characters, so "Bon - [P2026-096] Zilk Ultra
 * Soft" came out as "Bon -  P2026-096  Zilk Ultra So". The filename carries the
 * campaign instead, where the full name fits.
 */
const SHEET_NAME = 'Comments';

/** Strips what a filesystem would reject, keeping Thai intact. */
function fileName(campaignName: string): string {
  const clean = campaignName.replace(/[\\/:*?"<>|]/g, '').trim();
  const today = stamp(new Date().toISOString()).slice(0, 10);
  return `${clean || 'comments'} - comments ${today}.xlsx`;
}

export async function downloadCommentsExcel(
  data: CommentExportResponse,
  campaignName: string,
): Promise<void> {
  const xlsx = await import('xlsx');

  const aoa: (string | number)[][] = [COLUMNS.map((c) => c.header)];
  for (const r of data.rows) {
    aoa.push([
      r.kol,
      r.platform === 'tiktok' ? 'TikTok' : r.platform === 'facebook' ? 'Facebook' : r.platform,
      // Falls back to the code, then to a marker: an unclassified comment must
      // appear in the sheet rather than as a blank that reads like a bug.
      r.label || r.category || 'ยังไม่จัดประเภท',
      r.theme ?? '',
      r.text,
      r.author ?? '',
      r.likes,
      r.is_reply ? 'ใช่' : '',
      stamp(r.posted_at),
      r.post_url ?? '',
    ]);
  }

  const sheet = xlsx.utils.aoa_to_sheet(aoa);
  sheet['!cols'] = COLUMNS.map((c) => ({ wch: c.width }));
  // Filter dropdowns on the header row: the team's whole reason for wanting a
  // spreadsheet is to slice by KOL or by ประเภท themselves. Only when there is
  // data — an autofilter over a header-only sheet makes Excel warn on open.
  if (aoa.length > 1) {
    sheet['!autofilter'] = {
      ref: xlsx.utils.encode_range({
        s: { r: 0, c: 0 },
        e: { r: aoa.length - 1, c: COLUMNS.length - 1 },
      }),
    };
  }

  const wb = xlsx.utils.book_new();
  xlsx.utils.book_append_sheet(wb, sheet, SHEET_NAME);
  xlsx.writeFile(wb, fileName(campaignName));
}
