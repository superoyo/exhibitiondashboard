import type { ReportRecordDerived } from '@kol/shared';

import { tierOf } from './tier';

/**
 * Stat rows → a downloaded .xlsx, replacing the CSV export (team ask,
 * 2026-09-14: "ไฟล์ Excel ใช้งานง่ายกว่า"). Same SheetJS-in-the-browser
 * pattern as commentExcel.ts — no server dependency, no BOM/mojibake traps,
 * loaded on demand because SheetJS is ~120 kB gzipped.
 */

const COLUMNS: { header: string; width: number }[] = [
  { header: 'หมวด', width: 18 },
  { header: 'KOL', width: 22 },
  { header: 'ชื่อ', width: 22 },
  { header: 'แพลตฟอร์ม', width: 12 },
  { header: 'Followers', width: 12 },
  { header: 'ระดับ', width: 8 },
  { header: 'Views', width: 12 },
  { header: 'Likes', width: 10 },
  { header: 'Comments', width: 10 },
  { header: 'Shares', width: 10 },
  { header: 'Saves', width: 10 },
  { header: 'Engagement', width: 12 },
  { header: 'ER%', width: 8 },
  { header: 'โพสต์เมื่อ', width: 12 },
  { header: 'ลิงก์โพสต์', width: 46 },
];

/** Excel forbids : \ / ? * [ ] in sheet names and caps them at 31 chars, so
 *  the tab stays generic and the filename carries the campaign. */
const SHEET_NAME = 'Stats';

function fileName(campaignName: string): string {
  const clean = campaignName.replace(/[\\/:*?"<>|]/g, '').trim();
  const today = new Date().toISOString().slice(0, 10);
  return `${clean || 'campaign'} - stats ${today}.xlsx`;
}

export async function downloadReportExcel(
  rows: ReportRecordDerived[],
  campaignName: string,
): Promise<void> {
  const xlsx = await import('xlsx');

  const aoa: (string | number)[][] = [COLUMNS.map((c) => c.header)];
  for (const r of rows) {
    aoa.push([
      r.category,
      `@${r.username}`,
      r.nickname,
      r.platform_label,
      r.followers,
      tierOf(r.followers)?.label ?? '',
      r.views,
      // hidden like counts export as "ซ่อน", never as a fabricated 0
      r.likesHidden ? 'ซ่อน' : r.likes,
      r.comments,
      r.shares,
      r.saves,
      r.engagement,
      r.erUnavailable ? '' : Number(r.er.toFixed(2)),
      r.posted,
      r.url,
    ]);
  }

  const sheet = xlsx.utils.aoa_to_sheet(aoa);
  sheet['!cols'] = COLUMNS.map((c) => ({ wch: c.width }));
  // Filter dropdowns on the header row — the point of asking for Excel is to
  // slice by group or platform without re-importing anything.
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
