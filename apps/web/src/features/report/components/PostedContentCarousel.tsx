import { useCallback, useEffect, useRef, useState } from 'react';
import type { ReportRecordDerived } from '@kol/shared';

import { CachedImage } from '@/components/common/CachedImage';
import { PlatformBadge } from '@/components/common/PlatformBadge';
import type { CategoryColors } from '@/lib/colors';

/** Scrolling one card at a time is too slow with 20+ influencers in a campaign. */
const CARDS_PER_MOVE = 3;
const AUTO_MS = 3000;
const CARD_WIDTH = 300;
const GAP = 12;
const THUMB_MIN = 30;

/**
 * "Posted Content" — the influencer view's replacement for the Top-3 podium.
 *
 * Everyone who has posted gets a card, so this is a horizontal track rather
 * than a 3-up grid: an influencer opens the link to see their own content is
 * up, which only works if every card is reachable. No medals and no metric
 * numbers — ranking the influencers against each other is a client concern.
 *
 * The track auto-advances so the page is readable without touching it (e.g. on
 * a screen in the office), and pauses while the pointer is over it or while the
 * thumb is being dragged, so it never fights the person using it.
 */
export function PostedContentCarousel({
  rows,
  colors,
  emptyLabel,
}: {
  rows: ReportRecordDerived[];
  colors: CategoryColors;
  /** Description of the active filter, shown when nothing matches. */
  emptyLabel: string;
}) {
  const track = useRef<HTMLDivElement>(null);
  const bar = useRef<HTMLDivElement>(null);
  const [thumb, setThumb] = useState({ width: THUMB_MIN, left: 0, visible: false });
  const [canPrev, setCanPrev] = useState(false);
  const [canNext, setCanNext] = useState(false);
  const paused = useRef(false);

  const step = () => {
    const card = track.current?.querySelector<HTMLElement>('[data-card]');
    return ((card?.getBoundingClientRect().width ?? CARD_WIDTH) + GAP) * CARDS_PER_MOVE;
  };
  const maxScroll = () => {
    const el = track.current;
    return el ? Math.max(0, el.scrollWidth - el.clientWidth) : 0;
  };

  /** Keep the arrows and the thumb in sync with wherever the track is now. */
  const sync = useCallback(() => {
    const el = track.current;
    if (!el) return;
    const max = maxScroll();
    setCanPrev(el.scrollLeft > 2);
    setCanNext(el.scrollLeft < max - 2);

    // The bar stays mounted (hidden via CSS) so this ref always exists. Making
    // its presence depend on `visible` deadlocks: no bar -> no measurement ->
    // never visible -> no bar.
    const barEl = bar.current;
    const barWidth = barEl?.clientWidth ?? 0;
    const ratio = el.scrollWidth > 0 ? el.clientWidth / el.scrollWidth : 1;
    const width = Math.max(THUMB_MIN, Math.round(barWidth * ratio));
    setThumb({
      width,
      left: Math.round((max > 0 ? el.scrollLeft / max : 0) * (barWidth - width)),
      visible: max > 2,
    });
  }, []);

  useEffect(() => {
    sync();
    const el = track.current;
    el?.addEventListener('scroll', sync);
    window.addEventListener('resize', sync);
    // Card images load after mount and can change the track's width, which
    // moves the thumb — ResizeObserver catches that; a one-shot measure does not.
    const observer = el ? new ResizeObserver(sync) : null;
    if (el && observer) observer.observe(el);
    return () => {
      el?.removeEventListener('scroll', sync);
      window.removeEventListener('resize', sync);
      observer?.disconnect();
    };
  }, [sync, rows.length]);

  useEffect(() => {
    const timer = setInterval(() => {
      const el = track.current;
      if (!el || paused.current) return;
      const max = maxScroll();
      if (max <= 2) return;
      // Loop back rather than stopping at the end, so an unattended screen
      // keeps cycling through everyone.
      if (el.scrollLeft >= max - 2) el.scrollTo({ left: 0, behavior: 'smooth' });
      else el.scrollBy({ left: step(), behavior: 'smooth' });
    }, AUTO_MS);
    return () => clearInterval(timer);
  }, []);

  /** Drag the thumb (or click the track) to move the carousel. */
  const startDrag = (startX: number) => {
    const barEl = bar.current;
    const el = track.current;
    if (!barEl || !el) return;
    paused.current = true;
    const barWidth = barEl.clientWidth;
    const travel = barWidth - thumb.width;
    const startLeft = thumb.left;

    const move = (x: number) => {
      const next = Math.min(Math.max(0, startLeft + (x - startX)), travel);
      el.scrollLeft = (travel > 0 ? next / travel : 0) * maxScroll();
    };
    const onMouseMove = (e: MouseEvent) => move(e.clientX);
    const onTouchMove = (e: TouchEvent) => {
      const touch = e.touches[0];
      if (touch) move(touch.clientX);
    };
    const stop = () => {
      paused.current = false;
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', stop);
      document.removeEventListener('touchmove', onTouchMove);
      document.removeEventListener('touchend', stop);
    };
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', stop);
    document.addEventListener('touchmove', onTouchMove);
    document.addEventListener('touchend', stop);
  };

  if (rows.length === 0) {
    return (
      <div className="text-sm text-muted-foreground">
        ไม่มีโพสต์ในตัวกรอง &quot;<b>{emptyLabel}</b>&quot;
      </div>
    );
  }

  return (
    <div
      className="relative"
      onMouseEnter={() => (paused.current = true)}
      onMouseLeave={() => (paused.current = false)}
    >
      <div
        ref={track}
        className="flex snap-x snap-mandatory gap-3 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {rows.map((row) => (
          <ContentCard
            key={`${row.username}-${row.platform}`}
            row={row}
            color={colors.colorOf(row.category)}
          />
        ))}
      </div>

      <CarouselArrow
        side="left"
        show={canPrev}
        onClick={() => track.current?.scrollBy({ left: -step(), behavior: 'smooth' })}
      />
      <CarouselArrow
        side="right"
        show={canNext}
        onClick={() => track.current?.scrollBy({ left: step(), behavior: 'smooth' })}
      />

      <div
        ref={bar}
        className="relative mt-3.5 h-2 w-full cursor-pointer rounded-full bg-slate-200"
        style={{ display: thumb.visible ? 'block' : 'none' }}
        onClick={(e) => {
          const el = track.current;
          if (!el || e.target !== e.currentTarget) return;
          const rect = e.currentTarget.getBoundingClientRect();
          const ratio = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
          el.scrollLeft = ratio * maxScroll();
        }}
      >
        <div
          role="presentation"
          className="absolute top-0 h-full cursor-grab rounded-full bg-slate-400 hover:bg-slate-500 active:cursor-grabbing active:bg-slate-600"
          style={{ width: thumb.width, left: thumb.left }}
          onMouseDown={(e) => {
            e.preventDefault();
            startDrag(e.clientX);
          }}
          onTouchStart={(e) => {
            const touch = e.touches[0];
            if (touch) startDrag(touch.clientX);
          }}
        />
      </div>
    </div>
  );
}

function CarouselArrow({
  side,
  show,
  onClick,
}: {
  side: 'left' | 'right';
  show: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={side === 'left' ? 'เลื่อนไปทางซ้าย' : 'เลื่อนไปทางขวา'}
      onClick={onClick}
      className="absolute top-1/2 z-[5] flex size-10 -translate-y-1/2 items-center justify-center rounded-full border border-border bg-white text-base font-bold text-slate-900 shadow-[0_2px_10px_rgba(15,23,42,.18)] hover:bg-slate-100"
      style={{ [side]: -6, visibility: show ? 'visible' : 'hidden' }}
    >
      {side === 'left' ? '❮' : '❯'}
    </button>
  );
}

/** Same card as the podium, minus the medal and every metric. */
function ContentCard({ row, color }: { row: ReportRecordDerived; color: string }) {
  return (
    <div
      data-card
      className="w-[300px] max-w-[85%] flex-none snap-start overflow-hidden rounded-[14px] border border-border bg-card shadow-card"
    >
      <a
        href={row.url || undefined}
        target="_blank"
        rel="noopener noreferrer"
        className="relative block h-[190px] overflow-hidden bg-slate-200"
      >
        <div className="absolute inset-0 flex items-center justify-center text-[0.8rem] text-slate-400">
          ตัวอย่างคอนเทนต์
        </div>
        <CachedImage src={row.thumb} className="relative block h-[190px] w-full object-cover" />
        <span className="chip absolute right-2 top-3" style={{ background: color }}>
          {row.category}
        </span>
        <div
          className="absolute inset-x-0 bottom-0 px-3 py-2 text-sm font-semibold text-white"
          style={{ background: 'linear-gradient(transparent,rgba(0,0,0,.7))' }}
        >
          ▶ ดูคลิปจริง
        </div>
      </a>

      <div className="p-3">
        <div className="flex items-center gap-2">
          <CachedImage
            src={row.avatar}
            className="size-[42px] flex-none rounded-full bg-slate-200 object-cover"
            style={{ border: `2px solid ${color}` }}
          />
          <div className="min-w-0">
            <div className="truncate text-lg font-bold leading-tight">@{row.username}</div>
            <div className="truncate text-xs text-muted-foreground">{row.nickname || ''}</div>
            <div className="mt-1">
              <PlatformBadge platform={row.platform} label={row.platform_label} />
            </div>
          </div>
        </div>

        {row.url ? (
          <a href={row.url} target="_blank" rel="noopener noreferrer" className="post-link">
            🔗 ดูโพสต์ต้นทาง ↗
          </a>
        ) : (
          <span className="post-link disabled">— ยังไม่มีลิงก์โพสต์ —</span>
        )}
      </div>
    </div>
  );
}
