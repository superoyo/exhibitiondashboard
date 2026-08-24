import { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { TRACKER_GROUPS, type Campaign, type RosterKind } from '@kol/shared';

import { AppShell } from '@/components/layout/AppShell';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { routes } from '@/config/routes';
import { apiErrorMessage } from '@/lib/axios';
import { toast } from '@/stores/toastStore';
import { listCampaigns } from '@/features/campaigns/api/campaignsApi';
import { AddKolForm, type AddKolDraft } from '@/features/roster/components/AddKolForm';
import { ImportCard } from '@/features/roster/components/ImportCard';
import { RosterRow, type RosterRowDraft } from '@/features/roster/components/RosterRow';
import { parseLinksTextarea } from '@/features/roster/lib/importSync';
import {
  useAddRosterKol,
  useDeleteRosterKol,
  usePatchRosterKol,
  useRoster,
  useSheetLink,
} from '@/features/roster/hooks/useRoster';
import { useRosterImport } from '@/features/roster/hooks/useRosterImport';

/** Sentinel campaign value that selects the live Tracker roster instead. */
const TRACKER_SENTINEL = '__tracker';

const GROUP_LIST_ID = 'roster-group-list';
const SUB_LIST_ID = 'roster-sub-list';

export default function RosterPage() {
  const [searchParams] = useSearchParams();
  const urlCampaign = searchParams.get('campaign') ?? '';

  const kind: RosterKind = urlCampaign === TRACKER_SENTINEL ? 'tracker' : 'report';
  const isReport = kind === 'report';

  // Campaign metadata supplies the per-campaign group/subgroup vocabularies.
  const campaignsQuery = useQuery({
    queryKey: ['campaigns', 'list', 'searchable'] as const,
    queryFn: () => listCampaigns(100),
    enabled: isReport,
  });

  /**
   * Which campaign this page edits. Precedence, preserved from the legacy page:
   *   ?campaign=  >  the newest campaign  >  'sahagroup'
   * A campaign in the URL with no metadata row is still editable — it just gets
   * empty group lists rather than being refused.
   */
  const campaign = useMemo(() => {
    if (!isReport) return '';
    if (urlCampaign) return urlCampaign;
    return campaignsQuery.data?.[0]?.key ?? 'sahagroup';
  }, [isReport, urlCampaign, campaignsQuery.data]);

  const meta: Pick<Campaign, 'name' | 'emoji' | 'groups' | 'subgroups'> = useMemo(() => {
    if (!isReport) return { name: 'Tracker (live)', emoji: '📡', groups: [], subgroups: [] };
    const found = campaignsQuery.data?.find((c) => c.key === campaign);
    return found ?? { name: campaign, emoji: '📊', groups: [], subgroups: [] };
  }, [isReport, campaign, campaignsQuery.data]);

  const groups = isReport ? meta.groups : [...TRACKER_GROUPS];
  const subgroups = isReport ? meta.subgroups : [];
  const showSubgroup = isReport && subgroups.length > 0;

  const roster = useRoster(kind, campaign);
  const sheetLink = useSheetLink(campaign, isReport && Boolean(campaign));
  const importer = useRosterImport(campaign);

  const addKol = useAddRosterKol(kind, campaign);
  const patchKol = usePatchRosterKol(kind, campaign);
  const deleteKol = useDeleteRosterKol(kind, campaign);

  function handleAdd(draft: AddKolDraft) {
    const username = draft.username.trim();
    if (!username) {
      toast.error('ใส่ username ก่อน');
      return;
    }
    addKol.mutate(
      {
        username,
        display: draft.display.trim(),
        group: draft.group.trim() || groups[0] || '',
        ...(showSubgroup ? { subgroup: draft.subgroup.trim() } : {}),
        ...(isReport ? { url: draft.url.trim() } : {}),
      },
      {
        onSuccess: () => toast.success('เพิ่มแล้ว'),
        onError: (error) => toast.error(apiErrorMessage(error)),
      },
    );
  }

  function handleSave(id: number, draft: RosterRowDraft) {
    patchKol.mutate(
      {
        id,
        input: {
          display: draft.display,
          group: draft.group,
          active: draft.active,
          ...(showSubgroup ? { subgroup: draft.subgroup.trim() } : {}),
          ...(isReport ? { links: parseLinksTextarea(draft.linksText) } : {}),
          // -1 / '' = clear on the server; an emptied input really does erase.
          ...(isReport
            ? {
                cost_thb: draft.costText.trim() ? Number(draft.costText.replace(/,/g, '')) : -1,
                boost_thb: draft.boostText.trim() ? Number(draft.boostText.replace(/,/g, '')) : -1,
                kpi_metric: draft.kpiMetric,
                kpi_target: draft.kpiTargetText.trim()
                  ? Math.round(Number(draft.kpiTargetText.replace(/,/g, '')))
                  : -1,
              }
            : {}),
        },
      },
      {
        onSuccess: () => toast.success('บันทึกแล้ว'),
        onError: (error) => toast.error(apiErrorMessage(error)),
      },
    );
  }

  function handleDelete(id: number) {
    if (!window.confirm('ลบ KOL นี้?')) return;
    deleteKol.mutate(id, {
      onSuccess: () => toast.success('ลบแล้ว'),
      onError: (error) => toast.error(apiErrorMessage(error)),
    });
  }

  const backHref = isReport ? routes.campaign(campaign) : routes.tracker;
  const tabs = [
    { to: routes.home, label: '← Home', end: true },
    { to: backHref, label: '← กลับหน้ารายงาน' },
  ];

  const columnCount = 6 + (showSubgroup ? 1 : 0) + (isReport ? 2 : 0);
  const kols = roster.data ?? [];

  return (
    <AppShell tabs={tabs} className="max-w-6xl">
      <header className="mb-4">
        <h1 className="text-xl font-bold sm:text-2xl">
          ✏️ แก้ไขรายชื่อ KOL — {meta.emoji || '📊'} {meta.name}
        </h1>
        <p className="text-sm text-muted-foreground">
          เพิ่ม / แก้ไข / ปิด-เปิด / ลบ KOL ของแคมเปญนี้ · บันทึกลงฐานข้อมูลทันที
        </p>
      </header>

      {/* This page edits ONE roster only — no switcher, so other campaigns'
          rosters are never reachable from here. */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <span className="rounded-full border border-primary bg-primary px-4 py-1.5 text-sm font-semibold text-primary-foreground">
          {meta.emoji || '📊'} {meta.name}
        </span>
        <span className="text-xs text-muted-foreground">แก้ไขเฉพาะ KOL ของแคมเปญนี้เท่านั้น</span>
      </div>

      <p className="mb-3 text-xs text-muted-foreground">
        {isReport ? (
          <>
            📌 แคมเปญ <b>{meta.name}</b> · ใส่/แก้ <b>ลิงก์โพสต์</b> ของแต่ละ KOL แล้วไปหน้ารายงานกด{' '}
            <b>Refresh Data</b> (ติ๊ก active = รวมในรายงาน)
          </>
        ) : (
          'หน้านี้คุม KOL ที่ระบบ scrape live (kols) — แยกจากรายงานแคมเปญ'
        )}
      </p>

      {isReport && (
        <ImportCard
          linkedUrl={sheetLink.data ?? ''}
          busy={importer.busy}
          status={importer.status}
          onImportFile={(file) => void importer.importFile(file)}
          onImportUrl={(url) => void importer.importFromUrl(url)}
        />
      )}

      <AddKolForm
        groups={groups}
        showSubgroup={showSubgroup}
        showUrl={isReport}
        groupListId={GROUP_LIST_ID}
        subListId={SUB_LIST_ID}
        onAdd={handleAdd}
        pending={addKol.isPending}
      />

      {/* Native datalists give the same type-ahead the legacy inputs had. */}
      <datalist id={GROUP_LIST_ID}>
        {groups.map((g) => (
          <option key={g} value={g} />
        ))}
      </datalist>
      <datalist id={SUB_LIST_ID}>
        {subgroups.map((s) => (
          <option key={s} value={s} />
        ))}
      </datalist>

      <Card>
        <CardContent className="p-3">
          <div className="mb-2 flex items-center justify-between">
            <div className="text-sm font-semibold">
              รายชื่อ KOL{roster.isSuccess ? ` (${kols.length})` : ''}
            </div>
            <Button variant="outline" size="sm" onClick={() => void roster.refetch()}>
              ↻ โหลดใหม่
            </Button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-border text-left text-[0.85rem] text-muted-foreground">
                  <th className="whitespace-nowrap p-2 font-semibold">#</th>
                  <th className="whitespace-nowrap p-2 font-semibold">@username</th>
                  <th className="whitespace-nowrap p-2 font-semibold">ชื่อแสดง</th>
                  <th className="whitespace-nowrap p-2 font-semibold">กลุ่มใหญ่</th>
                  {showSubgroup && (
                    <th className="whitespace-nowrap p-2 font-semibold">กลุ่มย่อย</th>
                  )}
                  {isReport && (
                    <th className="whitespace-nowrap p-2 font-semibold">🔗 ลิงก์โพสต์</th>
                  )}
                  {isReport && (
                    <th className="whitespace-nowrap p-2 font-semibold">💰 การขาย (เฉพาะทีม)</th>
                  )}
                  <th className="whitespace-nowrap p-2 font-semibold">สถานะ</th>
                  <th className="whitespace-nowrap p-2 text-right font-semibold">จัดการ</th>
                </tr>
              </thead>
              <tbody>
                {roster.isLoading ? (
                  <tr>
                    <td colSpan={columnCount} className="p-2 text-muted-foreground">
                      กำลังโหลด…
                    </td>
                  </tr>
                ) : roster.isError ? (
                  <tr>
                    <td colSpan={columnCount} className="p-2 text-destructive">
                      โหลดไม่สำเร็จ: {apiErrorMessage(roster.error)}
                    </td>
                  </tr>
                ) : kols.length === 0 ? (
                  <tr>
                    <td colSpan={columnCount} className="p-2 text-muted-foreground">
                      ยังไม่มี KOL — เพิ่มด้านบน
                    </td>
                  </tr>
                ) : (
                  kols.map((kol, i) => (
                    <RosterRow
                      key={kol.id}
                      kol={kol}
                      index={i}
                      showSubgroup={showSubgroup}
                      showLinks={isReport}
                      groupListId={GROUP_LIST_ID}
                      subListId={SUB_LIST_ID}
                      onSave={handleSave}
                      onDelete={handleDelete}
                      saving={patchKol.isPending && patchKol.variables?.id === kol.id}
                      deleting={deleteKol.isPending && deleteKol.variables === kol.id}
                    />
                  ))
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </AppShell>
  );
}
