import { Fragment } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import type { PromoPack, PromoSlot, PromoSlotStatus } from '@kol/shared';

import { PlatformIcon } from '@/components/common/PlatformBadge';
import { cn } from '@/lib/utils';
import { expiryLabel, fmtSheetDate, leftOf, slotTitle } from '@/features/promo/lib/promo';

import { QuotaBar } from './QuotaBar';

export type SlotFilter = 'all' | PromoSlotStatus;

const STATUS: Record<PromoSlotStatus, { label: string; className: string }> = {
  used: { label: 'ลงแล้ว', className: 'bg-emerald-100 text-emerald-800' },
  reserved: { label: 'จอง', className: 'bg-amber-100 text-amber-800' },
  free: { label: 'ว่าง', className: 'bg-slate-100 text-slate-500' },
};

function SlotRow({ slot }: { slot: PromoSlot }) {
  const status = STATUS[slot.status];
  const title = slotTitle(slot);
  return (
    <div className="grid grid-cols-[2rem_4.25rem_minmax(0,1fr)] items-center gap-x-3 gap-y-1 border-t border-border px-4 py-2 text-sm sm:grid-cols-[2rem_4.25rem_minmax(0,1fr)_4.5rem_6rem_7rem]">
      <span className="tabular-nums text-muted-foreground">{slot.n}</span>
      <span
        className={cn(
          'rounded-full px-2 py-0.5 text-center text-xs font-semibold',
          status.className,
        )}
      >
        {status.label}
      </span>
      <div className="min-w-0">
        <div className={cn('truncate', !title && 'text-muted-foreground')} title={title}>
          {title || 'ยังไม่มีงานจอง'}
        </div>
        {(slot.status_text || slot.note) && (
          <div className="truncate text-xs text-muted-foreground" title={slot.note}>
            {slot.status_text && (
              <span className="mr-1.5 rounded bg-slate-100 px-1.5 py-px text-slate-600">
                {slot.status_text}
              </span>
            )}
            {slot.note}
          </div>
        )}
      </div>
      {/* On a phone these three wrap under the title, aligned with it. */}
      <span className="col-start-3 truncate text-xs text-muted-foreground sm:col-start-auto">
        {slot.buyer}
      </span>
      <span className="col-start-3 text-xs text-muted-foreground sm:col-start-auto">
        {fmtSheetDate(slot.date)}
      </span>
      <span className="col-start-3 flex flex-wrap items-center gap-2 sm:col-start-auto sm:justify-end">
        {slot.links.length > 0
          ? slot.links.map((link) => (
              <PlatformIcon key={link.url} platform={link.platform} href={link.url} />
            ))
          : slot.status === 'used' && (
              <span className="text-xs text-muted-foreground">ยังไม่ใส่ลิงก์</span>
            )}
      </span>
    </div>
  );
}

/**
 * One promotion page's quota: a summary line that is always visible, and the
 * numbered slots under it. Pages that are fully used start folded — the page
 * is about what is LEFT — but stay one click away.
 */
export function PackCard({
  pack,
  open,
  onToggle,
  filter,
}: {
  pack: PromoPack;
  open: boolean;
  onToggle: () => void;
  filter: SlotFilter;
}) {
  const left = leftOf(pack);
  const done = pack.used >= pack.quota;
  const slots = filter === 'all' ? pack.slots : pack.slots.filter((s) => s.status === filter);
  const expiry = expiryLabel(pack.expiry);
  const Chevron = open ? ChevronDown : ChevronRight;

  return (
    <section className="rounded-[14px] border border-border bg-card shadow-card">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full flex-wrap items-center gap-x-4 gap-y-2 rounded-[14px] px-4 py-3 text-left transition-colors hover:bg-slate-50"
      >
        <Chevron className="size-4 flex-none text-muted-foreground" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <div className="truncate font-bold">{pack.page}</div>
          {expiry && <div className="truncate text-xs text-muted-foreground">{expiry}</div>}
        </div>
        <div className="text-right">
          <div className="text-sm font-semibold">
            ลงแล้ว {pack.used} จาก {pack.quota}
          </div>
          <div className={cn('text-xs', done ? 'text-emerald-600' : 'text-muted-foreground')}>
            {done
              ? '✓ ใช้ครบแล้ว'
              : `เหลือ ${left} ครั้ง${pack.reserved > 0 ? ` (จองไว้ ${pack.reserved})` : ''}`}
          </div>
        </div>
        <QuotaBar counts={pack} className="w-full sm:w-40" />
      </button>

      {open &&
        (slots.length === 0 ? (
          <div className="border-t border-border px-4 py-3 text-sm text-muted-foreground">
            ไม่มีรายการในกลุ่มนี้
          </div>
        ) : (
          slots.map((slot, index) => {
            const section = slot.section;
            const showSection = section !== '' && section !== (slots[index - 1]?.section ?? '');
            return (
              <Fragment key={`${slot.n}-${index}`}>
                {showSection && (
                  <div className="border-t border-border bg-slate-50 px-4 py-1 text-xs font-semibold text-slate-600">
                    {section}
                  </div>
                )}
                <SlotRow slot={slot} />
              </Fragment>
            );
          })
        ))}
    </section>
  );
}
