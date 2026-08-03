import { cn } from '@/lib/utils';

/** The curated icon set from the legacy create-campaign modal. */
export const CAMPAIGN_EMOJIS = [
  '📊',
  '🧴',
  '💄',
  '🪥',
  '🦷',
  '👁️',
  '🚿',
  '🧼',
  '🥛',
  '🧃',
  '🍊',
  '☕',
  '🍞',
  '🍬',
  '🥗',
  '🍽️',
  '🍜',
  '🏃',
  '🏋️',
  '💪',
  '🐶',
  '🐱',
  '🧺',
  '👗',
  '🛍️',
  '🎬',
  '🏠',
  '🎮',
  '📱',
  '⚽',
  '✈️',
  '🎨',
  '🎵',
  '📷',
  '🚗',
  '💼',
] as const;

export const DEFAULT_CAMPAIGN_EMOJI = '📊';

export function EmojiPicker({
  value,
  onChange,
}: {
  value: string;
  onChange: (emoji: string) => void;
}) {
  return (
    <div className="grid grid-cols-8 gap-1.5" role="radiogroup" aria-label="Emoji / ไอคอน">
      {CAMPAIGN_EMOJIS.map((emoji) => {
        const selected = emoji === value;
        return (
          <button
            key={emoji}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-label={emoji}
            onClick={() => onChange(emoji)}
            className={cn(
              'rounded-lg border p-1.5 text-xl transition-colors',
              selected ? 'border-primary bg-primary' : 'border-border bg-white hover:bg-slate-100',
            )}
          >
            {emoji}
          </button>
        );
      })}
    </div>
  );
}
