import type { ReportRecordDerived } from '@kol/shared';

import { tierOf } from './tier';

/** Column order of the exported CSV. `tier` is computed, not on the record. */
const COLUMNS = [
  'category',
  'username',
  'nickname',
  'followers',
  'tier',
  'views',
  'likes',
  'comments',
  'shares',
  'saves',
  'engagement',
  'er',
  'posted',
  'url',
] as const;

/** Values a report cell can hold once read off a record. */
type CellValue = string | number | boolean | null | undefined;

/** RFC-4180 escaping: double the quotes, wrap when a delimiter is present. */
function escapeCell(value: CellValue): string {
  const text = (value == null ? '' : String(value)).replace(/"/g, '""');
  return /[",\n]/.test(text) ? `"${text}"` : text;
}

export function buildReportCsv(rows: ReportRecordDerived[]): string {
  const lines = [COLUMNS.join(',')];
  for (const row of rows) {
    lines.push(
      COLUMNS.map((col) => {
        if (col === 'er') return row.er.toFixed(2);
        if (col === 'tier') return escapeCell(tierOf(row.followers)?.label ?? '');
        // hidden like counts export as empty, not as a fabricated 0
        if (col === 'likes' && row.likesHidden) return '';
        return escapeCell(row[col]);
      }).join(','),
    );
  }
  return lines.join('\n');
}

/** Filesystem-safe filename stem from a campaign name. */
function safeStem(name: string): string {
  return (
    name
      .trim()
      .replace(/[^\p{L}\p{N}]+/gu, '_')
      .replace(/^_+|_+$/g, '')
      .slice(0, 60) || 'campaign_report'
  );
}

/**
 * Trigger a CSV download.
 *
 * The BOM matters: without it Excel opens the file as Latin-1 and every Thai
 * KOL name turns to mojibake.
 *
 * The filename is derived from the campaign. The legacy export hardcoded
 * `PAO_Super_Perfume_2026.csv`, so every other campaign downloaded under the
 * wrong name — that was a bug, not a convention.
 */
export function downloadReportCsv(rows: ReportRecordDerived[], campaignName: string): void {
  // U+FEFF is the UTF-8 BOM, written as an escape so it is visible in the source.
  const blob = new Blob([`\uFEFF${buildReportCsv(rows)}`], {
    type: 'text/csv;charset=utf-8',
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${safeStem(campaignName)}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}
