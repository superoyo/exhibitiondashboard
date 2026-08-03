import { Link } from 'react-router-dom';
import { Pencil, Trash2 } from 'lucide-react';
import type { Campaign } from '@kol/shared';

import { Badge } from '@/components/ui/badge';
import { routes } from '@/config/routes';
import { fmtDateTh } from '@/lib/format';

/** Group chips shown before collapsing into a "+N" badge. */
const MAX_GROUP_CHIPS = 4;

interface CampaignCardProps {
  campaign: Campaign;
  onEdit: (campaign: Campaign) => void;
  onArchive: (campaign: Campaign) => void;
  archiving: boolean;
}

/**
 * One campaign tile. The edit/archive buttons deliberately sit OUTSIDE the
 * <Link> so clicking them never navigates — in the legacy markup this was the
 * reason they were absolutely positioned siblings of the anchor.
 */
export function CampaignCard({ campaign, onEdit, onArchive, archiving }: CampaignCardProps) {
  const groups = campaign.groups ?? [];
  const visibleGroups = groups.slice(0, MAX_GROUP_CHIPS);
  const overflow = groups.length - visibleGroups.length;

  return (
    <div className="relative rounded-[14px] border border-border bg-card shadow-card transition-all duration-150 hover:-translate-y-0.5 hover:border-slate-400 hover:shadow-[0_6px_18px_rgba(15,23,42,.08)]">
      <button
        type="button"
        onClick={() => onEdit(campaign)}
        title="แก้ไขแคมเปญนี้"
        aria-label={`แก้ไขแคมเปญ ${campaign.name}`}
        className="absolute right-[2.9rem] top-2.5 z-[2] flex size-8 items-center justify-center rounded-lg border border-border bg-white text-slate-700 transition-colors hover:border-slate-400 hover:bg-slate-100"
      >
        <Pencil className="size-4" aria-hidden="true" />
      </button>
      <button
        type="button"
        onClick={() => onArchive(campaign)}
        disabled={archiving}
        title="ลบแคมเปญนี้"
        aria-label={`ลบแคมเปญ ${campaign.name}`}
        className="absolute right-2.5 top-2.5 z-[2] flex size-8 items-center justify-center rounded-lg border border-border bg-white text-destructive transition-colors hover:border-red-200 hover:bg-red-100 disabled:opacity-50"
      >
        {archiving ? '⏳' : <Trash2 className="size-4" aria-hidden="true" />}
      </button>

      <Link to={routes.campaign(campaign.key)} className="block p-5 text-inherit no-underline">
        <div className="flex items-start justify-between gap-2 pr-20">
          <div className="text-4xl">{campaign.emoji || '📊'}</div>
          <div className="text-right">
            <div className="text-xs text-muted-foreground">{fmtDateTh(campaign.created_at)}</div>
            <div className="mt-1 text-xs text-muted-foreground">
              {campaign.roster_count || 0} KOLs
            </div>
          </div>
        </div>

        <div className="mt-2 text-lg font-bold leading-tight">{campaign.name}</div>
        <div className="mt-1 text-xs text-muted-foreground">/c/{campaign.key}</div>

        {campaign.subtitle && (
          <div className="mt-2 text-sm text-slate-700">{campaign.subtitle}</div>
        )}

        {visibleGroups.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1">
            {visibleGroups.map((g) => (
              <Badge key={g} variant="soft">
                {g}
              </Badge>
            ))}
            {overflow > 0 && <Badge variant="soft">+{overflow}</Badge>}
          </div>
        )}

        {campaign.created_by && (
          <div className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
            {campaign.created_by_photo ? (
              <img
                src={campaign.created_by_photo}
                alt=""
                referrerPolicy="no-referrer"
                className="size-5 rounded-full bg-slate-200 object-cover"
                onError={(e) => e.currentTarget.remove()}
              />
            ) : (
              <span aria-hidden="true">👤</span>
            )}
            <span>สร้างโดย {campaign.created_by}</span>
          </div>
        )}

        <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
          <span>
            {campaign.refreshed_at
              ? `🔄 อัปเดต ${fmtDateTh(campaign.refreshed_at)}`
              : 'ยังไม่มีข้อมูล'}
          </span>
          <span className="font-semibold text-blue-600">เปิดรายงาน →</span>
        </div>
      </Link>
    </div>
  );
}
