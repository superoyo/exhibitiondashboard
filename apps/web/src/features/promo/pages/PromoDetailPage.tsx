import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ExternalLink, Pencil, RefreshCw } from 'lucide-react';

import { AppShell } from '@/components/layout/AppShell';
import { MAIN_TABS } from '@/components/layout/NavBar';
import { SegmentedControl } from '@/components/common/SegmentedControl';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { routes } from '@/config/routes';
import { apiErrorMessage } from '@/lib/axios';
import { toast } from '@/stores/toastStore';
import { PackCard, type SlotFilter } from '@/features/promo/components/PackCard';
import { PromoFormDialog } from '@/features/promo/components/PromoFormDialog';
import { QuotaBar } from '@/features/promo/components/QuotaBar';
import { useAutoSyncOne, usePromoDetail, useSyncPromo } from '@/features/promo/hooks/usePromo';
import { fmtSyncedAt, leftOf } from '@/features/promo/lib/promo';

function Tile({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: number;
  sub?: string;
  tone?: string;
}) {
  return (
    <Card className="p-4">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={`mt-0.5 text-3xl font-bold tabular-nums ${tone ?? ''}`}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-muted-foreground">{sub}</div>}
    </Card>
  );
}

/**
 * `/promotion-packages/:promoId` — one deal: how many posts were bought on
 * each promotion page, how many are used, and the link of every post.
 */
export default function PromoDetailPage() {
  const { promoId } = useParams();
  const id = Number(promoId);
  const detail = usePromoDetail(id);
  const autoSyncing = useAutoSyncOne(detail.data);
  const sync = useSyncPromo();

  const [filter, setFilter] = useState<SlotFilter>('all');
  // Explicit choices only; a page with nothing chosen follows the default
  // (open while it still has posts left).
  const [toggled, setToggled] = useState<Record<string, boolean>>({});
  const [editOpen, setEditOpen] = useState(false);

  const promo = detail.data;
  const syncing = autoSyncing || sync.isPending;

  function handleSync() {
    sync.mutate(id, {
      onSuccess: (fresh) => {
        if (fresh.sync_error) toast.error(`ดึงข้อมูลไม่สำเร็จ: ${fresh.sync_error}`);
        else toast.success('อัปเดตจากชีตแล้ว');
      },
      onError: (err) => toast.error(`อัปเดตไม่สำเร็จ: ${apiErrorMessage(err)}`),
    });
  }

  const isOpen = (page: string, hasLeft: boolean) =>
    filter !== 'all' ? true : (toggled[page] ?? hasLeft);
  const allOpen = promo ? promo.packs.every((p) => isOpen(p.page, p.used < p.quota)) : false;

  function setAll(open: boolean) {
    if (!promo) return;
    setToggled(Object.fromEntries(promo.packs.map((p) => [p.page, open])));
  }

  return (
    <AppShell tabs={MAIN_TABS} className="max-w-5xl py-5">
      <Link to={routes.promo} className="text-sm text-blue-600">
        ← งานทั้งหมด
      </Link>

      {detail.isLoading ? (
        <div className="mt-3 grid gap-3">
          <Skeleton className="h-8 w-1/2" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : detail.isError || !promo ? (
        <Card className="mt-3 p-6 text-destructive">
          เปิดงานนี้ไม่ได้: {apiErrorMessage(detail.error, 'ไม่พบงานนี้')}
        </Card>
      ) : (
        <>
          <header className="mb-4 mt-2 flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <h1 className="text-2xl font-bold">{promo.name}</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                {promo.team && <>ดูแลโดย {promo.team} · </>}
                อ่านจากชีตล่าสุด {fmtSyncedAt(promo.synced_at)}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={handleSync} disabled={syncing}>
                <RefreshCw className={syncing ? 'animate-spin' : undefined} aria-hidden="true" />
                {syncing ? 'กำลังอ่านชีต…' : 'อัปเดตข้อมูล'}
              </Button>
              <Button variant="outline" asChild>
                <a href={promo.sheet_url} target="_blank" rel="noopener noreferrer">
                  เปิดไฟล์ของทีม <ExternalLink aria-hidden="true" />
                </a>
              </Button>
              <Button
                variant="outline"
                size="icon"
                onClick={() => setEditOpen(true)}
                title="แก้ไขชื่อ / ลิงก์ไฟล์"
                aria-label="แก้ไขงานนี้"
              >
                <Pencil aria-hidden="true" />
              </Button>
            </div>
          </header>

          {promo.sync_error && (
            <Alert variant="warning" className="mb-4">
              <AlertDescription>
                ⚠️ <b>ดึงข้อมูลรอบล่าสุดไม่สำเร็จ:</b> {promo.sync_error}
                {promo.quota > 0 && <> — ตัวเลขด้านล่างเป็นของรอบก่อน</>}
              </AlertDescription>
            </Alert>
          )}
          {promo.warnings.length > 0 && (
            <Alert variant="warning" className="mb-4">
              <AlertDescription>
                {promo.warnings.map((w) => (
                  <div key={w}>⚠️ {w}</div>
                ))}
              </AlertDescription>
            </Alert>
          )}

          {promo.quota > 0 && (
            <>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <Tile
                  label="โควต้าทั้งหมด"
                  value={promo.quota}
                  sub={`ครั้ง · ${promo.pack_count} เพจ`}
                />
                <Tile label="ลงแล้ว" value={promo.used} tone="text-emerald-600" />
                <Tile
                  label="คงเหลือ"
                  value={leftOf(promo)}
                  sub={`จองไว้ ${promo.reserved} · ว่าง ${promo.free}`}
                />
              </div>
              <QuotaBar counts={promo} className="mt-3" />

              <div className="mb-3 mt-5 flex flex-wrap items-center justify-between gap-3">
                <SegmentedControl
                  label="ดูเฉพาะ"
                  value={filter}
                  onChange={(v) => setFilter(v as SlotFilter)}
                  options={[
                    { value: 'all', label: 'ทั้งหมด' },
                    { value: 'used', label: `ลงแล้ว (${promo.used})` },
                    { value: 'reserved', label: `จอง (${promo.reserved})` },
                    { value: 'free', label: `ว่าง (${promo.free})` },
                  ]}
                />
                {filter === 'all' && (
                  <Button variant="outline" size="sm" onClick={() => setAll(!allOpen)}>
                    {allOpen ? 'ย่อทั้งหมด' : 'ขยายทั้งหมด'}
                  </Button>
                )}
              </div>

              <div className="grid gap-3">
                {promo.packs.map((pack) => {
                  const hasLeft = pack.used < pack.quota;
                  const open = isOpen(pack.page, hasLeft);
                  return (
                    <PackCard
                      key={pack.page}
                      pack={pack}
                      open={open}
                      filter={filter}
                      onToggle={() => setToggled((t) => ({ ...t, [pack.page]: !open }))}
                    />
                  );
                })}
              </div>
            </>
          )}

          <PromoFormDialog open={editOpen} onOpenChange={setEditOpen} editing={promo} />
        </>
      )}
    </AppShell>
  );
}
