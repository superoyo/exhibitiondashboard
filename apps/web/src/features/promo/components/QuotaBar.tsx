import type { PromoCounts } from '@kol/shared';

import { cn } from '@/lib/utils';

/**
 * Used / reserved / free as one bar. Green is spent, amber is booked but not
 * posted, the grey remainder is unclaimed — the same three colours as the
 * status chips in the slot table, so the bar reads as a summary of the rows.
 */
export function QuotaBar({ counts, className }: { counts: PromoCounts; className?: string }) {
  const total = Math.max(1, counts.quota);
  const pct = (n: number) => `${(n / total) * 100}%`;
  return (
    <div
      className={cn('flex h-2 overflow-hidden rounded-full bg-slate-200', className)}
      role="img"
      aria-label={`ลงแล้ว ${counts.used} จาก ${counts.quota} ครั้ง จองไว้ ${counts.reserved}`}
    >
      <div className="bg-emerald-500" style={{ width: pct(counts.used) }} />
      <div className="bg-amber-400" style={{ width: pct(counts.reserved) }} />
    </div>
  );
}
