import type { PromoCounts, PromoSlot } from '@kol/shared';

/** A snapshot older than this is re-read when the page opens. */
export const STALE_MINUTES = 30;

export function isStale(syncedAt: string | null): boolean {
  if (!syncedAt) return true;
  const t = new Date(syncedAt).getTime();
  return Number.isNaN(t) || Date.now() - t > STALE_MINUTES * 60_000;
}

/** Posts still unspent — reserved ones included: a booking is not a post. */
export function leftOf(c: PromoCounts): number {
  return Math.max(0, c.quota - c.used);
}

/** "17 พ.ย. 15:40" — when the sheet was last read. */
export function fmtSyncedAt(iso: string | null): string {
  if (!iso) return 'ยังไม่เคยดึงข้อมูล';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const day = d.toLocaleDateString('th-TH', { day: 'numeric', month: 'short' });
  const time = d.toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' });
  return `${day} ${time}`;
}

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

/** Real date cells arrive as ISO and are shown the Thai way; anything the team
 *  typed as text ("5 August 2026", "10 Oct") is shown exactly as typed. */
export function fmtSheetDate(text: string): string {
  const m = ISO_DATE.exec(text);
  if (!m) return text;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return d.toLocaleDateString('th-TH', { day: 'numeric', month: 'short', year: '2-digit' });
}

/** Expiry is a date in most sheets and a sentence in some. */
export function expiryLabel(expiry: string): string {
  if (!expiry) return '';
  return /^\d/.test(expiry) ? `หมดอายุ ${fmtSheetDate(expiry)}` : expiry;
}

/** Brand and job as the team wrote them, whichever exist. */
export function slotTitle(slot: PromoSlot): string {
  return [slot.account, slot.campaign].filter(Boolean).join(' · ');
}
