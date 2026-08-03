import { useEffect, useRef, useState } from 'react';
import type { EChartsOption } from 'echarts';

import { cn } from '@/lib/utils';

/** Minimal surface of an ECharts instance that this wrapper needs. */
interface ChartInstance {
  setOption: (option: EChartsOption, notMerge?: boolean) => void;
  resize: () => void;
  dispose: () => void;
}

interface EChartProps {
  option: EChartsOption;
  /** CSS height; charts need an explicit one because the container is empty. */
  height: number | string;
  className?: string;
  /** Accessible description of what the chart shows. */
  ariaLabel?: string;
}

/**
 * The single ECharts wrapper for the whole app.
 *
 * ECharts is ~1 MB, so the library is imported on demand rather than bundled
 * into the page chunk — charts only render once their data has loaded anyway.
 *
 * Options are applied with `notMerge: true`, matching the legacy pages: series
 * are rebuilt from scratch on each render, so a merge would leave stale series
 * behind when the filtered dataset shrinks.
 */
export function EChart({ option, height, className, ariaLabel }: EChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ChartInstance | null>(null);
  const [ready, setReady] = useState(false);

  // Create the instance once, after the library resolves.
  useEffect(() => {
    let cancelled = false;
    let observer: ResizeObserver | undefined;

    void (async () => {
      const echarts = await import('echarts');
      if (cancelled || !containerRef.current) return;

      const instance = echarts.init(containerRef.current, null, {
        renderer: 'canvas',
      }) as unknown as ChartInstance;
      chartRef.current = instance;
      setReady(true);

      // A ResizeObserver handles sidebar/table reflow, which a window `resize`
      // listener alone would miss.
      observer = new ResizeObserver(() => instance.resize());
      observer.observe(containerRef.current);
    })();

    return () => {
      cancelled = true;
      observer?.disconnect();
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!ready) return;
    chartRef.current?.setOption(option, true);
  }, [option, ready]);

  return (
    <div
      ref={containerRef}
      className={cn('w-full', className)}
      style={{ height }}
      role="img"
      aria-label={ariaLabel}
    />
  );
}
