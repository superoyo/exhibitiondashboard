import type { ActiveJob } from '@kol/shared';
import { useState } from 'react';

import { useActiveJobs } from '@/features/report/hooks/useReport';
import { cn } from '@/lib/utils';

/**
 * Floating status dock. Lives in the page frame, so it shows on every internal
 * page: a job takes minutes and whoever started it has usually navigated away
 * by the time it finishes.
 *
 * Styling is the app's own theme, not new colours — brand gold for work in
 * progress (the same gold as the page background and focus ring), `state.ok` /
 * `state.error` for the two endings, and `shadow-popup`, which exists in the
 * theme for exactly this kind of floating panel.
 */
const TONE = {
  running: {
    icon: '⏳',
    ring: 'border-brand',
    chip: 'bg-brand-200 text-[#8a6a00]',
    bar: 'bg-brand',
  },
  success: {
    icon: '✅',
    ring: 'border-state-ok/40',
    chip: 'bg-emerald-50 text-state-ok',
    bar: 'bg-state-ok',
  },
  failed: {
    icon: '⚠️',
    ring: 'border-state-error/40',
    chip: 'bg-red-50 text-state-error',
    bar: 'bg-state-error',
  },
} as const;

function elapsed(startedAt: string | null): string {
  if (!startedAt) return '';
  const ms = Date.now() - new Date(startedAt).getTime();
  if (!Number.isFinite(ms) || ms < 0) return '';
  const min = Math.floor(ms / 60000);
  if (min < 1) return 'เพิ่งเริ่ม';
  if (min < 60) return `${min} นาทีที่แล้ว`;
  return `${Math.floor(min / 60)} ชม. ${min % 60} นาทีที่แล้ว`;
}

function JobCard({ job }: { job: ActiveJob }) {
  const tone = TONE[job.status === 'running' ? 'running' : job.status === 'failed' ? 'failed' : 'success'];
  // A bar only when the denominator is real. During the scrape nobody knows how
  // many comments a post holds, so a percentage there would be invented.
  const pct = job.total > 0 ? Math.min(100, Math.round((100 * job.done) / job.total)) : null;

  return (
    <div className={cn('rounded-lg border-l-4 bg-card p-3 shadow-card', tone.ring)}>
      <div className="mb-1 flex items-start gap-2">
        <span className="text-base leading-none">{tone.icon}</span>
        <div className="min-w-0 flex-1">
          <div className="line-clamp-2 break-words text-sm font-bold leading-snug">
            {job.emoji} {job.campaign_name}
          </div>
          <span
            className={cn(
              'mt-0.5 inline-block rounded px-1.5 py-0.5 text-[10px] font-bold',
              tone.chip,
            )}
          >
            {job.kind_label}
          </span>
        </div>
      </div>

      {/* Wraps instead of truncating — the old one-line status was cut off with
          an ellipsis exactly where the numbers were. */}
      <p className="whitespace-pre-wrap break-words text-xs text-muted-foreground">{job.message}</p>

      {pct !== null ? (
        <div className="mt-2">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
            <div
              className={cn('h-full rounded-full transition-all duration-500', tone.bar)}
              style={{ width: `${pct}%` }}
            />
          </div>
          <div className="mt-1 flex justify-between text-[10px] tabular-nums text-muted-foreground">
            <span>
              {job.done.toLocaleString()} / {job.total.toLocaleString()}
            </span>
            <span className="font-bold">{pct}%</span>
          </div>
        </div>
      ) : null}

      <div className="mt-1.5 flex items-center justify-between text-[10px] text-muted-foreground">
        <span>{job.status === 'running' ? elapsed(job.started_at) : 'เสร็จแล้ว'}</span>
        {job.cost_usd ? <span>💸 ${job.cost_usd}</span> : null}
      </div>
    </div>
  );
}

export function JobStatusDock() {
  const [hidden, setHidden] = useState(false);
  const jobs = useActiveJobs();
  const list = jobs.data ?? [];

  if (list.length === 0) return null;

  const running = list.filter((j) => j.status === 'running').length;

  if (hidden) {
    return (
      <button
        type="button"
        onClick={() => setHidden(false)}
        className="fixed bottom-4 right-4 z-50 rounded-full border border-brand bg-card px-3 py-2 text-xs font-bold shadow-popup"
      >
        {running > 0 ? `⏳ ${running} งานกำลังทำ` : '✅ ดูผลงานล่าสุด'}
      </button>
    );
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 w-[min(20rem,calc(100vw-2rem))]">
      <div className="rounded-xl border border-brand-400 bg-brand-200/70 p-2 shadow-popup backdrop-blur">
        <div className="mb-1.5 flex items-center justify-between px-1">
          <span className="text-xs font-bold text-[#7a5c00]">
            {running > 0 ? `กำลังทำงาน ${running} งาน` : 'งานที่เพิ่งเสร็จ'}
          </span>
          <button
            type="button"
            onClick={() => setHidden(true)}
            className="rounded px-1.5 text-xs font-bold text-[#7a5c00] hover:bg-brand-300"
            aria-label="ซ่อนกล่องสถานะ"
          >
            ✕
          </button>
        </div>
        {/* Capped height so a campaign with several jobs cannot cover the page */}
        <div className="max-h-[60vh] space-y-2 overflow-y-auto">
          {list.map((job) => (
            <JobCard key={job.key} job={job} />
          ))}
        </div>
      </div>
    </div>
  );
}
