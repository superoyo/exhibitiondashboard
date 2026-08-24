import { useEffect, useState } from 'react';
import type { RosterKol } from '@kol/shared';

import { Button } from '@/components/ui/button';
import { hashColor } from '@/lib/colors';
import { cn } from '@/lib/utils';

interface RosterRowProps {
  kol: RosterKol;
  index: number;
  showSubgroup: boolean;
  showLinks: boolean;
  groupListId: string;
  subListId: string;
  onSave: (id: number, draft: RosterRowDraft) => void;
  onDelete: (id: number) => void;
  saving: boolean;
  deleting: boolean;
}

export interface RosterRowDraft {
  display: string;
  group: string;
  subgroup: string;
  active: boolean;
  /** Raw textarea contents: one link per line. */
  linksText: string;
  /** Commercial fields, kept as input text — '' means "no value". */
  costText: string;
  boostText: string;
  /** Two KPI slots — one KOL can be sold on Views AND Engagement at once. */
  kpis: { metric: string; targetText: string }[];
}

function draftFrom(kol: RosterKol): RosterRowDraft {
  return {
    display: kol.display ?? '',
    group: kol.group ?? '',
    subgroup: kol.subgroup ?? '',
    active: kol.active,
    // Fall back to the legacy single `url` when a row predates links_json.
    linksText: (kol.links ?? []).map((l) => l.url).join('\n') || (kol.url ?? ''),
    costText: kol.cost_thb != null ? String(kol.cost_thb) : '',
    boostText: kol.boost_thb != null ? String(kol.boost_thb) : '',
    kpis: [0, 1].map((i) => ({
      metric: kol.kpis?.[i]?.metric ?? '',
      targetText: kol.kpis?.[i]?.target != null ? String(kol.kpis[i].target) : '',
    })),
  };
}

const inputClass =
  'w-full rounded-lg border border-border bg-white px-2.5 py-1.5 text-[0.85rem] ' +
  'focus-visible:border-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand';

/** One editable roster row. Edits are local until บันทึก is pressed. */
export function RosterRow({
  kol,
  index,
  showSubgroup,
  showLinks,
  groupListId,
  subListId,
  onSave,
  onDelete,
  saving,
  deleting,
}: RosterRowProps) {
  const [draft, setDraft] = useState<RosterRowDraft>(() => draftFrom(kol));

  // Re-sync when the server row changes (after a save or a reload), so the row
  // never keeps showing a stale local edit as if it had been persisted.
  useEffect(() => setDraft(draftFrom(kol)), [kol]);

  const set = <K extends keyof RosterRowDraft>(key: K, value: RosterRowDraft[K]) =>
    setDraft((d) => ({ ...d, [key]: value }));

  const linkRows = Math.max(1, (kol.links ?? []).length);

  return (
    <tr className="border-b border-border">
      <td className="p-2 text-muted-foreground">{index + 1}</td>
      <td className="p-2 font-medium">@{kol.username}</td>
      <td className="p-2">
        <input
          className={inputClass}
          aria-label={`ชื่อแสดงของ @${kol.username}`}
          value={draft.display}
          onChange={(e) => set('display', e.target.value)}
        />
      </td>
      <td className="p-2">
        <input
          className={cn(inputClass, 'min-w-[120px]')}
          aria-label={`กลุ่มใหญ่ของ @${kol.username}`}
          list={groupListId}
          value={draft.group}
          onChange={(e) => set('group', e.target.value)}
        />
      </td>
      {showSubgroup && (
        <td className="p-2">
          <input
            className={cn(inputClass, 'min-w-[130px]')}
            aria-label={`กลุ่มย่อยของ @${kol.username}`}
            list={subListId}
            value={draft.subgroup}
            onChange={(e) => set('subgroup', e.target.value)}
          />
        </td>
      )}
      {showLinks && (
        <td className="p-2">
          <textarea
            className={cn(inputClass, 'min-w-[250px] text-[0.78rem] leading-snug')}
            rows={linkRows}
            aria-label={`ลิงก์โพสต์ของ @${kol.username}`}
            placeholder="1 บรรทัด = 1 ลิงก์ (TikTok / FB / IG / YT / X / เว็บ)"
            value={draft.linksText}
            onChange={(e) => set('linksText', e.target.value)}
          />
        </td>
      )}
      {showLinks && (
        // Commercial mini-form (report roster only — the tracker has no sales).
        // Stacked so the row does not get another four columns wide.
        <td className="min-w-[170px] p-2">
          <div className="space-y-1">
            <input
              className={cn(inputClass, 'py-1 text-[0.78rem]')}
              inputMode="decimal"
              aria-label={`ค่าตัว (บาท) ของ @${kol.username}`}
              placeholder="ค่าตัว (บาท)"
              value={draft.costText}
              onChange={(e) => set('costText', e.target.value)}
            />
            <input
              className={cn(inputClass, 'py-1 text-[0.78rem]')}
              inputMode="decimal"
              aria-label={`งบบูสต์ (บาท) ของ @${kol.username}`}
              placeholder="บูส (บาท)"
              value={draft.boostText}
              onChange={(e) => set('boostText', e.target.value)}
            />
            {draft.kpis.map((slot, i) => (
              <div key={i} className="flex gap-1">
                <select
                  className={cn(inputClass, 'w-[88px] px-1 py-1 text-[0.75rem]')}
                  aria-label={`หน่วย KPI ที่ ${i + 1} ของ @${kol.username}`}
                  value={slot.metric}
                  onChange={(e) =>
                    set(
                      'kpis',
                      draft.kpis.map((s, j) => (j === i ? { ...s, metric: e.target.value } : s)),
                    )
                  }
                >
                  <option value="">KPI: —</option>
                  <option value="views">Views</option>
                  <option value="impressions">Imp</option>
                  <option value="interaction">Interaction</option>
                  <option value="reach">Reach</option>
                </select>
                <input
                  className={cn(inputClass, 'py-1 text-[0.78rem]')}
                  inputMode="numeric"
                  aria-label={`เป้า KPI ที่ ${i + 1} ของ @${kol.username}`}
                  placeholder="เป้า"
                  value={slot.targetText}
                  onChange={(e) =>
                    set(
                      'kpis',
                      draft.kpis.map((s, j) =>
                        j === i ? { ...s, targetText: e.target.value } : s,
                      ),
                    )
                  }
                />
              </div>
            ))}
          </div>
        </td>
      )}
      <td className="p-2">
        <label className="flex items-center gap-1.5 text-xs">
          <input
            type="checkbox"
            checked={draft.active}
            onChange={(e) => set('active', e.target.checked)}
            aria-label={`เปิดใช้งาน @${kol.username}`}
          />
          <span className="chip" style={{ background: hashColor(draft.subgroup || draft.group) }}>
            {draft.active ? 'active' : 'ปิด'}
          </span>
        </label>
      </td>
      <td className="whitespace-nowrap p-2 text-right">
        <Button size="sm" onClick={() => onSave(kol.id, draft)} disabled={saving}>
          บันทึก
        </Button>{' '}
        <Button
          size="sm"
          variant="outline"
          className="border-red-200 text-destructive hover:bg-red-50"
          onClick={() => onDelete(kol.id)}
          disabled={deleting}
        >
          ลบ
        </Button>
      </td>
    </tr>
  );
}
