import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import type { PromoCampaignSummary } from '@kol/shared';

import { AppShell } from '@/components/layout/AppShell';
import { MAIN_TABS } from '@/components/layout/NavBar';
import { SegmentedControl } from '@/components/common/SegmentedControl';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { routes } from '@/config/routes';
import { apiErrorMessage } from '@/lib/axios';
import { toast } from '@/stores/toastStore';
import { PromoCard } from '@/features/promo/components/PromoCard';
import { PromoFormDialog } from '@/features/promo/components/PromoFormDialog';
import {
  useAutoSyncAll,
  usePromoList,
  useRemovePromo,
  useSyncAllPromos,
} from '@/features/promo/hooks/usePromo';
import { leftOf } from '@/features/promo/lib/promo';

type Tab = 'open' | 'done';

/**
 * `/promotion-packages` — which deals still have promotion-page posts left.
 *
 * Deals whose quota is fully used drop out of the default view (the team asked
 * for exactly this, 2026-11-17) and live under the second tab, so "what did we
 * finish" is one click rather than gone. A deal whose sheet has never been
 * read counts as open: hiding it would hide the fact that it needs fixing.
 */
export default function PromoListPage() {
  const navigate = useNavigate();
  const list = usePromoList();
  const autoSyncing = useAutoSyncAll(list.isSuccess);
  const syncAll = useSyncAllPromos();
  const remove = useRemovePromo();

  const [tab, setTab] = useState<Tab>('open');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<PromoCampaignSummary | null>(null);
  const [removingId, setRemovingId] = useState<number | null>(null);

  const { open, done } = useMemo(() => {
    const all = list.data ?? [];
    return {
      // Most posts left first: that is where the next job will be booked.
      open: all.filter((p) => !p.complete).sort((a, b) => leftOf(b) - leftOf(a)),
      done: all.filter((p) => p.complete),
    };
  }, [list.data]);
  const shown = tab === 'open' ? open : done;
  const leftTotal = open.reduce((sum, p) => sum + leftOf(p), 0);
  const syncing = autoSyncing || syncAll.isPending;

  function handleSyncAll() {
    syncAll.mutate(undefined, {
      onSuccess: (result) => {
        const failed = result.campaigns.filter((c) => c.sync_error).length;
        if (failed > 0) toast.error(`อัปเดตแล้ว แต่มี ${failed} งานที่ยังดึงข้อมูลไม่ได้`);
        else toast.success(`อัปเดตจากชีตแล้ว ${result.synced} งาน`);
      },
      onError: (err) => toast.error(`อัปเดตไม่สำเร็จ: ${apiErrorMessage(err)}`),
    });
  }

  function handleRemove(promo: PromoCampaignSummary) {
    const confirmed = window.confirm(
      `เอางาน "${promo.name}" ออกจากหน้านี้ใช่ไหม?\n\n` +
        'ไฟล์ชีตของทีมไม่ถูกแตะต้อง — ถ้าต้องการกลับมา กดเพิ่มงานแล้ววางลิงก์เดิมได้',
    );
    if (!confirmed) return;
    setRemovingId(promo.id);
    remove.mutate(promo.id, {
      onSuccess: () => toast.success(`เอางาน "${promo.name}" ออกแล้ว`),
      onError: (err) => toast.error(`ไม่สำเร็จ: ${apiErrorMessage(err)}`),
      onSettled: () => setRemovingId(null),
    });
  }

  return (
    <AppShell tabs={MAIN_TABS} className="max-w-6xl py-5">
      <header className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold sm:text-3xl">📦 Promotion Page Package</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            โควต้าลงโพสต์เพจโปรโมชั่นที่ลูกค้าซื้อไว้ — นับจากชีตของทีมแต่ละคน (ระบบอ่านอย่างเดียว
            ไม่แก้ไขไฟล์)
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={handleSyncAll} disabled={syncing}>
            <RefreshCw className={syncing ? 'animate-spin' : undefined} aria-hidden="true" />
            {syncing ? 'กำลังอ่านชีต…' : 'อัปเดตทั้งหมด'}
          </Button>
          <Button
            onClick={() => {
              setEditing(null);
              setDialogOpen(true);
            }}
            className="rounded-[10px] px-4 font-bold"
          >
            + เพิ่มงาน
          </Button>
        </div>
      </header>

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <SegmentedControl
          ariaLabel="เลือกกลุ่มงาน"
          value={tab}
          onChange={(v) => setTab(v as Tab)}
          options={[
            { value: 'open', label: `ยังเหลือโควต้า (${open.length})` },
            { value: 'done', label: `ใช้ครบแล้ว (${done.length})` },
          ]}
        />
        {tab === 'open' && open.length > 0 && (
          <span className="text-sm text-muted-foreground">
            เหลือรวม <b className="text-foreground">{leftTotal}</b> ครั้ง จาก {open.length} งาน
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {list.isLoading ? (
          Array.from({ length: 2 }, (_, i) => (
            <Card key={i} className="p-5">
              <Skeleton className="h-5 w-2/3" />
              <Skeleton className="mt-4 h-8 w-1/3" />
              <Skeleton className="mt-3 h-2 w-full" />
              <Skeleton className="mt-4 h-3 w-full" />
            </Card>
          ))
        ) : list.isError ? (
          <Card className="col-span-full p-6 text-destructive">
            โหลดไม่สำเร็จ: {apiErrorMessage(list.error)}
          </Card>
        ) : shown.length === 0 ? (
          <Card className="col-span-full p-8 text-center">
            {tab === 'done' ? (
              <div className="font-semibold">ยังไม่มีงานที่ใช้โควต้าครบ</div>
            ) : (list.data ?? []).length === 0 ? (
              <>
                <div className="mb-1 font-semibold">ยังไม่มีงานในหน้านี้</div>
                <div className="text-sm text-muted-foreground">
                  กด &quot;+ เพิ่มงาน&quot; แล้ววางลิงก์ไฟล์เช็กโควต้าของทีม
                </div>
              </>
            ) : (
              <div className="font-semibold">ทุกงานใช้โควต้าครบแล้ว</div>
            )}
          </Card>
        ) : (
          shown.map((promo) => (
            <PromoCard
              key={promo.id}
              promo={promo}
              onEdit={(p) => {
                setEditing(p);
                setDialogOpen(true);
              }}
              onRemove={handleRemove}
              removing={removingId === promo.id}
            />
          ))
        )}
      </div>

      <PromoFormDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        editing={editing}
        onSaved={(detail) => {
          if (!editing) navigate(routes.promoDetail(detail.id));
        }}
      />
    </AppShell>
  );
}
