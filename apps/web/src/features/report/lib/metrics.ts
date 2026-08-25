import type { ReportRecord, ReportRecordDerived } from '@kol/shared';

/**
 * Derived report metrics.
 *
 * The engagement-rate rules are the subtlest thing on this page and are ported
 * verbatim. Getting them wrong silently changes every ER figure a client sees:
 *
 *   - views > 0            → engagement / views
 *   - views == 0, eng > 0, followers > 0
 *                          → engagement / followers, marked with `*`
 *   - views == 0, eng > 0, followers == 0
 *                          → unavailable; the UI shows an em dash
 *   - views == 0, eng == 0 → 0.00% (a genuine zero, not "unknown")
 *
 * The middle case exists because photo posts on Facebook/Instagram expose no
 * view count at all, so an ER of 0 there would be a fabrication.
 */
export function derive(records: ReportRecord[]): ReportRecordDerived[] {
  return records.map((r) => {
    // Negative counts are the scrapers' "hidden" sentinel — Instagram returns
    // likes = -1 when the creator hides like counts. Clamped here ONCE so no
    // sum, chart, CSV or ER downstream ever subtracts a phantom like; the flag
    // lets the table say "ซ่อน" instead of a fabricated 0.
    const likesHidden = r.likes < 0;
    const likes = Math.max(0, r.likes);
    const comments = Math.max(0, r.comments);
    const shares = Math.max(0, r.shares);
    const saves = Math.max(0, r.saves || 0);
    const engagement = likes + comments + shares + saves;
    const byFollowers = !r.views && engagement > 0 && r.followers > 0;
    const er = r.views
      ? (engagement / r.views) * 100
      : byFollowers
        ? (engagement / r.followers) * 100
        : 0;
    return {
      ...r,
      likes,
      comments,
      shares,
      saves,
      likesHidden,
      engagement,
      er,
      erByFollowers: byFollowers,
      erUnavailable: !r.views && engagement > 0 && !r.followers,
    };
  });
}

/** Display string for a row's ER, including the `*` and em-dash conventions. */
export function erText(row: ReportRecordDerived): string {
  if (row.erUnavailable) return '—';
  return `${row.er.toFixed(2)}%${row.erByFollowers ? '*' : ''}`;
}

/** Sum a numeric field across rows, treating missing values as 0. */
export function sumBy(
  rows: ReportRecordDerived[],
  key: 'views' | 'likes' | 'comments' | 'shares' | 'saves' | 'engagement',
): number {
  return rows.reduce((total, r) => total + (r[key] || 0), 0);
}

export interface ReportTotals {
  totalViews: number;
  totalEngagement: number;
  /** Weighted overall ER: total engagement / total views, NOT a mean of ERs. */
  avgEr: number;
  postCount: number;
  kolCount: number;
  /** Sum of each KOL's LARGEST per-platform follower count. */
  reach: number;
}

export function computeTotals(rows: ReportRecordDerived[]): ReportTotals {
  const totalViews = sumBy(rows, 'views');
  const totalEngagement = sumBy(rows, 'engagement');

  // A KOL appears once per platform they posted on, and each row may carry a
  // different follower count. Counting every row would multiply one audience;
  // each KOL is therefore counted once, at their largest platform.
  const largestPerKol = new Map<string, number>();
  for (const r of rows) {
    largestPerKol.set(r.username, Math.max(largestPerKol.get(r.username) ?? 0, r.followers || 0));
  }

  return {
    totalViews,
    totalEngagement,
    avgEr: totalViews ? (totalEngagement / totalViews) * 100 : 0,
    postCount: rows.length,
    kolCount: new Set(rows.map((r) => r.username)).size,
    reach: [...largestPerKol.values()].reduce((a, b) => a + b, 0),
  };
}

/** Per-category engagement totals, used by the category charts. */
export interface CategoryTotals {
  views: number;
  engagement: number;
  likes: number;
  comments: number;
  shares: number;
  saves: number;
  count: number;
}

export function totalsByCategory(rows: ReportRecordDerived[]): Map<string, CategoryTotals> {
  const out = new Map<string, CategoryTotals>();
  for (const r of rows) {
    const t = out.get(r.category) ?? {
      views: 0,
      engagement: 0,
      likes: 0,
      comments: 0,
      shares: 0,
      saves: 0,
      count: 0,
    };
    t.views += r.views;
    t.engagement += r.engagement;
    t.likes += r.likes;
    t.comments += r.comments;
    t.shares += r.shares;
    t.saves += r.saves || 0;
    t.count += 1;
    out.set(r.category, t);
  }
  return out;
}

/** Distinct categories in first-seen order — also the filter/legend order. */
export function distinctCategories(rows: ReportRecordDerived[]): string[] {
  return [...new Set(rows.map((r) => r.category))];
}

/** Distinct platforms in first-seen order. */
export function distinctPlatforms(rows: ReportRecordDerived[]): string[] {
  return [...new Set(rows.map((r) => r.platform))];
}
