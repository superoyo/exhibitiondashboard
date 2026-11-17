import { Link } from 'react-router-dom';
import { Pencil, Trash2 } from 'lucide-react';
import type { PromoCampaignSummary } from '@kol/shared';

import { routes } from '@/config/routes';
import { cn } from '@/lib/utils';
import { fmtSyncedAt, leftOf } from '@/features/promo/lib/promo';

import { QuotaBar } from './QuotaBar';

interface PromoCardProps {
  promo: PromoCampaignSummary;
  onEdit: (promo: PromoCampaignSummary) => void;
  onRemove: (promo: PromoCampaignSummary) => void;
  removing: boolean;
}

/**
 * One deal on the overview. The headline is what is LEFT, because that is the
 * question the page exists to answer; each page of the deal gets its own line
 * so "which page still has posts" needs no click. Edit/remove sit outside the
 * link, as on the Home cards, so pressing them never navigates.
 */
export function PromoCard({ promo, onEdit, onRemove, removing }: PromoCardProps) {
  const left = leftOf(promo);
  const unread = promo.quota === 0;

  return (
    <div className="relative rounded-[14px] border border-border bg-card shadow-card transition-all duration-150 hover:-translate-y-0.5 hover:border-slate-400 hover:shadow-[0_6px_18px_rgba(15,23,42,.08)]">
      <button
        type="button"
        onClick={() => onEdit(promo)}
        title="แก้ไขชื่อ / ลิงก์ไฟล์"
        aria-label={`แก้ไขงาน ${promo.name}`}
        className="absolute right-[2.9rem] top-2.5 z-[2] flex size-8 items-center justify-center rounded-lg border border-border bg-white text-slate-700 transition-colors hover:border-slate-400 hover:bg-slate-100"
      >
        <Pencil className="size-4" aria-hidden="true" />
      </button>
      <button
        type="button"
        onClick={() => onRemove(promo)}
        disabled={removing}
        title="เอางานนี้ออกจากหน้านี้"
        aria-label={`เอางาน ${promo.name} ออก`}
        className="absolute right-2.5 top-2.5 z-[2] flex size-8 items-center justify-center rounded-lg border border-border bg-white text-destructive transition-colors hover:border-red-200 hover:bg-red-100 disabled:opacity-50"
      >
        {removing ? '⏳' : <Trash2 className="size-4" aria-hidden="true" />}
      </button>

      <Link to={routes.promoDetail(promo.id)} className="block p-5 text-inherit no-underline">
        <div className="pr-20">
          <div className="text-lg font-bold leading-tight">{promo.name}</div>
          {promo.team && (
            <div className="mt-0.5 text-xs text-muted-foreground">ดูแลโดย {promo.team}</div>
          )}
        </div>

        {unread ? (
          <div className="mt-3 rounded-lg border border-orange-200 bg-orange-50 p-3 text-sm text-orange-800">
            ⚠️ ยังดึงข้อมูลจากชีตไม่ได้
            {promo.sync_error && <div className="mt-1 text-xs">{promo.sync_error}</div>}
          </div>
        ) : (
          <>
            <div className="mt-3 flex items-baseline justify-between gap-3">
              <div>
                {promo.complete ? (
                  <span className="text-2xl font-bold text-emerald-600">ใช้ครบแล้ว</span>
                ) : (
                  <>
                    <span className="text-xs text-muted-foreground">เหลือ </span>
                    <span className="text-3xl font-bold">{left}</span>
                    <span className="text-sm text-muted-foreground"> ครั้ง</span>
                  </>
                )}
              </div>
              <div className="text-right text-xs text-muted-foreground">
                ลงแล้ว <b className="text-foreground">{promo.used}</b> จาก {promo.quota}
                {promo.reserved > 0 && <div>จองไว้ {promo.reserved}</div>}
              </div>
            </div>
            <QuotaBar counts={promo} className="mt-2" />

            <ul className="mt-3 grid gap-1">
              {promo.packs.map((pack) => {
                const done = pack.used >= pack.quota;
                return (
                  <li
                    key={pack.page}
                    className={cn(
                      'flex items-center justify-between gap-3 text-sm',
                      done && 'text-muted-foreground',
                    )}
                  >
                    <span className="min-w-0 truncate">{pack.page}</span>
                    <span className="flex-none tabular-nums">
                      {done ? (
                        <span title="ใช้ครบแล้ว">
                          ✓ ครบ {pack.used}/{pack.quota}
                        </span>
                      ) : (
                        <>
                          เหลือ <b>{pack.quota - pack.used}</b>{' '}
                          <span className="text-xs text-muted-foreground">
                            ({pack.used}/{pack.quota})
                          </span>
                        </>
                      )}
                    </span>
                  </li>
                );
              })}
            </ul>

            {promo.sync_error && (
              <div className="mt-3 text-xs text-orange-700">
                ⚠️ ดึงข้อมูลรอบล่าสุดไม่สำเร็จ — ตัวเลขนี้เป็นของรอบก่อน
              </div>
            )}
          </>
        )}

        <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
          <span>🔄 {fmtSyncedAt(promo.synced_at)}</span>
          <span className="font-semibold text-blue-600">ดูรายละเอียด →</span>
        </div>
      </Link>
    </div>
  );
}
