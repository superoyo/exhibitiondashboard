/**
 * Number formatting, ported verbatim from the legacy pages' `fmt` helper.
 * The thresholds and decimal places are deliberate — changing them would
 * change every KPI tile and chart label on the report.
 */
export function fmt(n: number | null | undefined): string {
  const v = n ?? 0;
  if (v >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
  return String(v);
}

/**
 * The Tracker's number format — deliberately different from `fmt`.
 *
 * It switches to compact notation only at 10k (so 4-digit counts stay exact)
 * and renders null as an en dash rather than 0, because on the Tracker a
 * missing value means "not scraped", not "zero".
 */
export function fmtCompact(n: number | null | undefined): string {
  if (n == null) return '–';
  return new Intl.NumberFormat('en', {
    notation: Math.abs(n) >= 10000 ? 'compact' : 'standard',
    maximumFractionDigits: 1,
  }).format(n);
}

/** Signed delta with a direction arrow, e.g. "▲3.7%". '' when null. */
export function fmtDeltaPct(n: number | null | undefined): string {
  if (n == null) return '';
  const arrow = n > 0 ? '▲' : n < 0 ? '▼' : '';
  return `${arrow}${Math.abs(n).toFixed(1)}%`;
}

/** Tailwind text colour for a delta: green up, red down, muted flat/null. */
export function deltaClass(n: number | null | undefined): string {
  if (n == null || n === 0) return 'text-muted-foreground';
  return n > 0 ? 'text-state-ok' : 'text-state-error';
}

/** Full grouped number, as used in the report table cells. */
export function fmtFull(n: number | null | undefined): string {
  return (n ?? 0).toLocaleString();
}

export function fmtPercent(n: number | null | undefined, digits = 2): string {
  return `${(n ?? 0).toFixed(digits)}%`;
}

/**
 * Masked-secret display. The backend already masks the value; this is only for
 * the placeholder shown before it loads.
 */
export const MASK_PLACEHOLDER = '…';

/** Thai-locale date for "data as of" lines. Returns '' for null/invalid input. */
export function fmtDateTh(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString('th-TH', { year: 'numeric', month: 'short', day: 'numeric' });
}
