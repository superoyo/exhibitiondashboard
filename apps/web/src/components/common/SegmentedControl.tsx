import { cn } from '@/lib/utils';

export interface SegmentOption {
  value: string;
  label: string;
}

/**
 * Pill-button filter row — the legacy `.seg` / `segs()` helper.
 * Used for the report's category, platform and metric selectors.
 */
export function SegmentedControl({
  options,
  value,
  onChange,
  label,
  ariaLabel,
  className,
}: {
  options: SegmentOption[];
  value: string;
  onChange: (value: string) => void;
  /** Inline caption rendered before the buttons, e.g. "หมวด:". */
  label?: string;
  ariaLabel?: string;
  className?: string;
}) {
  return (
    <div
      role="group"
      aria-label={ariaLabel ?? label}
      className={cn('flex flex-wrap items-center gap-2', className)}
    >
      {label && <span className="mr-1 text-xs font-semibold text-muted-foreground">{label}</span>}
      {options.map((opt) => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(opt.value)}
            className={cn(
              'rounded-full border px-3 py-1.5 text-[0.8rem] transition-colors',
              active
                ? 'border-primary bg-primary text-primary-foreground'
                : 'border-border bg-white hover:border-slate-400',
            )}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
