import { TRACKER_GROUP_COLORS, TRACKER_GROUP_FILTERS } from '@kol/shared';

import { cn } from '@/lib/utils';

/** "All" has no brand colour of its own — it uses the muted slate. */
const ALL_COLOR = '#64748b';

export function GroupChips({
  value,
  onChange,
}: {
  value: string;
  onChange: (group: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label="กรองตามกลุ่ม">
      {TRACKER_GROUP_FILTERS.map((group) => {
        const active = value === group;
        const color = group === 'All' ? ALL_COLOR : (TRACKER_GROUP_COLORS[group] ?? ALL_COLOR);
        return (
          <button
            key={group}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(group)}
            className={cn(
              'whitespace-nowrap rounded-full border px-3.5 py-1.5 text-[0.8rem] transition-colors',
              active ? 'border-transparent text-white' : 'border-border hover:bg-slate-100',
            )}
            style={active ? { background: color } : undefined}
          >
            {group}
          </button>
        );
      })}
    </div>
  );
}
