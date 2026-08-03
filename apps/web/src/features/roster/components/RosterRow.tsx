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
}

function draftFrom(kol: RosterKol): RosterRowDraft {
  return {
    display: kol.display ?? '',
    group: kol.group ?? '',
    subgroup: kol.subgroup ?? '',
    active: kol.active,
    // Fall back to the legacy single `url` when a row predates links_json.
    linksText: (kol.links ?? []).map((l) => l.url).join('\n') || (kol.url ?? ''),
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
