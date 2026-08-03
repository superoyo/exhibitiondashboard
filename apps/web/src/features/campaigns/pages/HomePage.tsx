import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search } from 'lucide-react';
import type { Campaign } from '@kol/shared';

import { AppShell } from '@/components/layout/AppShell';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { routes } from '@/config/routes';
import { apiErrorMessage } from '@/lib/axios';
import { useDebounce } from '@/hooks/useDebounce';
import { toast } from '@/stores/toastStore';
import { CampaignCard } from '@/features/campaigns/components/CampaignCard';
import { CampaignFormDialog } from '@/features/campaigns/components/CampaignFormDialog';
import {
  useArchiveCampaign,
  useLatestCampaigns,
  useSearchableCampaigns,
} from '@/features/campaigns/hooks/useCampaigns';

const HOME_TABS = [
  { to: routes.home, label: 'Home', end: true },
  // Same three tabs the legacy home page had — without this, /kol-list is only
  // reachable by typing the URL.
  { to: routes.kolList, label: 'KOL List' },
  { to: routes.settings, label: 'Apify Token' },
];

function matches(campaign: Campaign, query: string): boolean {
  return (
    (campaign.name ?? '').toLowerCase().includes(query) ||
    (campaign.key ?? '').toLowerCase().includes(query) ||
    (campaign.subtitle ?? '').toLowerCase().includes(query)
  );
}

export default function HomePage() {
  const navigate = useNavigate();

  const [search, setSearch] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Campaign | null>(null);

  const query = useDebounce(search).trim().toLowerCase();
  const searching = query.length > 0;

  const latest = useLatestCampaigns();
  // Only fetches once the user actually types — same lazy behaviour as the
  // legacy page's SEARCH_CACHE.
  const searchable = useSearchableCampaigns(searching);

  const results = useMemo(() => {
    if (!searching) return latest.data ?? [];
    return (searchable.data ?? []).filter((c) => matches(c, query));
  }, [searching, query, latest.data, searchable.data]);

  const archive = useArchiveCampaign();
  const [archivingKey, setArchivingKey] = useState<string | null>(null);

  function handleArchive(campaign: Campaign) {
    const confirmed = window.confirm(
      `ต้องการลบแคมเปญ "${campaign.name}" (/c/${campaign.key}) ออกจากระบบใช่ไหม?\n\n` +
        'แคมเปญจะหายไปจากหน้า Home ทันที (ข้อมูล KOL ยังถูกเก็บไว้ในระบบ กู้คืนได้ภายหลัง)',
    );
    if (!confirmed) return;

    setArchivingKey(campaign.key);
    archive.mutate(campaign.key, {
      onSuccess: () => toast.success(`ลบแคมเปญ "${campaign.name}" แล้ว`),
      onError: (err) => toast.error(`ลบไม่สำเร็จ: ${apiErrorMessage(err)}`),
      onSettled: () => setArchivingKey(null),
    });
  }

  function openCreate() {
    setEditing(null);
    setDialogOpen(true);
  }

  function openEdit(campaign: Campaign) {
    setEditing(campaign);
    setDialogOpen(true);
  }

  const searchHint = (() => {
    if (!searching) return '';
    if (searchable.isLoading) return 'กำลังค้นหา…';
    if (searchable.isError) return `ค้นหาไม่สำเร็จ: ${apiErrorMessage(searchable.error)}`;
    return `พบ ${results.length} แคมเปญ จากทั้งหมด ${searchable.data?.length ?? 0}`;
  })();

  return (
    <AppShell tabs={HOME_TABS} className="max-w-6xl py-5">
      <header className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-2xl font-bold sm:text-3xl">Home</h1>
        <Button onClick={openCreate} className="rounded-[10px] px-4 py-2.5 font-bold">
          + สร้างแคมเปญใหม่
        </Button>
      </header>

      <div className="mb-4">
        <div className="relative">
          <Search
            aria-hidden="true"
            className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            className="pl-9 text-[0.9rem]"
            placeholder="ค้นหา Campaign report… (พิมพ์ชื่อแคมเปญหรือ key)"
            autoComplete="off"
            aria-label="ค้นหาแคมเปญ"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="mt-1 min-h-[1.2em] text-xs text-muted-foreground">{searchHint}</div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {latest.isLoading && !searching ? (
          Array.from({ length: 3 }, (_, i) => (
            <Card key={i} className="p-5">
              <Skeleton className="h-10 w-10" />
              <Skeleton className="mt-3 h-5 w-3/4" />
              <Skeleton className="mt-2 h-3 w-1/3" />
              <Skeleton className="mt-4 h-3 w-full" />
            </Card>
          ))
        ) : latest.isError && !searching ? (
          <Card className="col-span-full p-6 text-destructive">
            โหลดไม่สำเร็จ: {apiErrorMessage(latest.error)}
          </Card>
        ) : results.length === 0 ? (
          <Card className="col-span-full p-8 text-center">
            <div className="mb-2 text-3xl">{searching ? '🔍' : '📭'}</div>
            {searching ? (
              <div className="font-semibold">ไม่พบแคมเปญที่ตรงกับ &quot;{query}&quot;</div>
            ) : (
              <>
                <div className="mb-1 font-semibold">ยังไม่มีแคมเปญ</div>
                <div className="text-sm text-muted-foreground">
                  กด &quot;+ สร้างแคมเปญใหม่&quot; ด้านบนเพื่อเริ่ม
                </div>
              </>
            )}
          </Card>
        ) : (
          results.map((campaign) => (
            <CampaignCard
              key={campaign.key}
              campaign={campaign}
              onEdit={openEdit}
              onArchive={handleArchive}
              archiving={archivingKey === campaign.key}
            />
          ))
        )}
      </div>

      <CampaignFormDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        editing={editing}
        // Brief pause so the success toast is actually readable before the
        // report page takes over (the legacy page waited 400ms for this too).
        onCreated={(campaign) => setTimeout(() => navigate(routes.campaign(campaign.key)), 400)}
      />
    </AppShell>
  );
}
