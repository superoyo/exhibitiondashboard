import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { apiErrorMessage } from '@/lib/axios';
import { toast } from '@/stores/toastStore';
import { getGroupKpis, saveGroupKpi } from '@/features/roster/api/rosterApi';

/**
 * KPI sold on a whole GROUP — "7M Impressions across Micro Package". It belongs
 * to no roster row, and the planner sheets write it as merged/summary cells the
 * row-wise import cannot own, so the team keys it in here: one line per group,
 * two KPI slots each (a group can be sold on two units at once).
 *
 * The group list comes from the roster's CURRENT groups plus any group that
 * already has a KPI stored — so a renamed group's orphaned KPI stays visible
 * (marked) instead of silently lingering in the database.
 */

const METRIC_OPTIONS = [
  { value: '', label: 'KPI: —' },
  { value: 'views', label: 'Views' },
  { value: 'impressions', label: 'Imp' },
  { value: 'interaction', label: 'Interaction' },
  { value: 'reach', label: 'Reach' },
] as const;

interface Slot {
  metric: string;
  targetText: string;
}

const inputClass =
  'rounded-lg border border-border bg-white px-2 py-1 text-[0.8rem] ' +
  'focus-visible:border-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand';

function GroupRow({
  campaign,
  group,
  initial,
  orphaned,
}: {
  campaign: string;
  group: string;
  initial: { metric: string; target: number }[];
  orphaned: boolean;
}) {
  const qc = useQueryClient();
  const [slots, setSlots] = useState<Slot[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setSlots(
      [0, 1].map((i) => ({
        metric: initial[i]?.metric ?? '',
        targetText: initial[i]?.target != null ? String(initial[i].target) : '',
      })),
    );
  }, [initial]);

  async function save() {
    setBusy(true);
    try {
      await saveGroupKpi(
        campaign,
        group,
        slots
          .filter((s) => s.targetText.trim())
          .map((s) => ({
            metric: s.metric,
            target: Math.round(Number(s.targetText.replace(/,/g, ''))) || 0,
          })),
      );
      await qc.invalidateQueries({ queryKey: ['roster', 'groupkpi', campaign] });
      toast.success(`บันทึก KPI กลุ่ม ${group} แล้ว`);
    } catch (error) {
      toast.error(apiErrorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="min-w-[140px] text-sm font-medium">
        {group}
        {orphaned ? (
          <span className="ml-1 text-[10px] text-amber-700">
            (ไม่มี KOL ใช้ชื่อกลุ่มนี้แล้ว — เคลียร์เป้าทิ้งได้)
          </span>
        ) : null}
      </span>
      {slots.map((slot, i) => (
        <span key={i} className="flex items-center gap-1">
          <select
            className={inputClass}
            aria-label={`หน่วย KPI ที่ ${i + 1} ของกลุ่ม ${group}`}
            value={slot.metric}
            onChange={(e) =>
              setSlots(slots.map((s, j) => (j === i ? { ...s, metric: e.target.value } : s)))
            }
          >
            {METRIC_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <input
            className={`${inputClass} w-28`}
            inputMode="numeric"
            placeholder="เป้ารวมทั้งกลุ่ม"
            aria-label={`เป้า KPI ที่ ${i + 1} ของกลุ่ม ${group}`}
            value={slot.targetText}
            onChange={(e) =>
              setSlots(slots.map((s, j) => (j === i ? { ...s, targetText: e.target.value } : s)))
            }
          />
        </span>
      ))}
      <Button size="sm" variant="outline" onClick={() => void save()} disabled={busy}>
        บันทึก
      </Button>
    </div>
  );
}

export function GroupKpiCard({ campaign, groups }: { campaign: string; groups: string[] }) {
  const stored = useQuery({
    queryKey: ['roster', 'groupkpi', campaign],
    queryFn: () => getGroupKpis(campaign),
    enabled: Boolean(campaign),
  });

  const data = stored.data ?? {};
  // Current roster groups first (stable order), then orphaned stored ones.
  const names = [...groups, ...Object.keys(data).filter((g) => !groups.includes(g))];
  if (names.length === 0) return null;

  return (
    <Card className="mb-4">
      <CardContent className="p-3">
        <div className="mb-1 text-sm font-semibold">📦 KPI ของแต่ละกลุ่ม (เฉพาะทีม)</div>
        <p className="mb-2 text-xs text-muted-foreground">
          สำหรับกลุ่มที่ขายเป็นยอดรวม เช่น แพ็กเกจการันตี 7,000,000 Impressions ทั้งกลุ่ม —
          หน้ารายงานจะเทียบกับผลรวมจริงของทุกคนในกลุ่มให้ (Imp/Reach เทียบไม่ได้ จะแสดงเป้าไว้เฉย ๆ)
        </p>
        <div className="space-y-2">
          {names.map((g) => (
            <GroupRow
              key={g}
              campaign={campaign}
              group={g}
              initial={data[g] ?? []}
              orphaned={!groups.includes(g)}
            />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
