/**
 * Category colours.
 *
 * Assignment is by index into the palette, not by hashing the category name —
 * the old hash approach let two categories in the same chart collide on one
 * colour. Building the map per render keeps that guarantee.
 */
export const CATEGORY_PALETTE = [
  '#6366f1',
  '#10b981',
  '#ec4899',
  '#f59e0b',
  '#06b6d4',
  '#8b5cf6',
  '#ef4444',
  '#14b8a6',
  '#3b82f6',
  '#84cc16',
  '#f43f5e',
  '#a855f7',
  '#0ea5e9',
  '#eab308',
  '#22c55e',
  '#fb7185',
] as const;

/** Colour for a category with no assignment (empty filter, unknown value). */
export const CATEGORY_FALLBACK = '#94a3b8';

/**
 * Roster pills use a SEPARATE, hash-based scheme from the report's index-based
 * palette. It is deliberately different: roster rows are edited one at a time
 * with no shared render pass, so a group must keep the same colour on its own —
 * collisions between two groups are acceptable there, unlike in a chart legend.
 */
const PILL_PALETTE = [
  '#6366f1',
  '#10b981',
  '#ec4899',
  '#f59e0b',
  '#06b6d4',
  '#8b5cf6',
  '#ef4444',
  '#14b8a6',
] as const;

export function hashColor(value: string | null | undefined): string {
  let h = 0;
  for (const ch of value ?? '') h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return PILL_PALETTE[h % PILL_PALETTE.length] ?? CATEGORY_FALLBACK;
}

export interface CategoryColors {
  /** Distinct categories, in first-seen order — also the legend/tab order. */
  categories: string[];
  colorOf: (category: string | null | undefined) => string;
}

/**
 * Build a stable category -> colour mapping for one render pass.
 * Order follows first appearance in `rows`, matching the legacy behaviour.
 */
export function buildCategoryColors(categories: Iterable<string>): CategoryColors {
  const unique = [...new Set(categories)];
  const map = new Map<string, string>();
  unique.forEach((category, i) => {
    map.set(category, CATEGORY_PALETTE[i % CATEGORY_PALETTE.length] ?? CATEGORY_FALLBACK);
  });
  return {
    categories: unique,
    colorOf: (category) =>
      category ? (map.get(category) ?? CATEGORY_FALLBACK) : CATEGORY_FALLBACK,
  };
}
