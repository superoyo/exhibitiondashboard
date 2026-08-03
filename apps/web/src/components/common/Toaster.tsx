import { useToastStore } from '@/stores/toastStore';
import { cn } from '@/lib/utils';

/** Bottom-right toast stack. Mounted once, at the app root. */
export function Toaster() {
  const toasts = useToastStore((s) => s.toasts);
  const dismiss = useToastStore((s) => s.dismiss);

  if (!toasts.length) return null;

  return (
    <div
      className="fixed bottom-4 right-4 z-[70] flex flex-col gap-2"
      role="status"
      aria-live="polite"
    >
      {toasts.map((t) => (
        <button
          key={t.id}
          type="button"
          onClick={() => dismiss(t.id)}
          className={cn(
            'rounded-[10px] border bg-white px-4 py-2 text-left text-sm shadow-[0_4px_14px_rgba(0,0,0,.08)]',
            'animate-in slide-in-from-bottom-2 fade-in',
            t.ok ? 'border-green-200' : 'border-red-200',
          )}
        >
          {t.ok ? '✅ ' : '⚠️ '}
          {t.message}
        </button>
      ))}
    </div>
  );
}
