import { create } from 'zustand';
import { FILTER_ALL, type ReportMetric } from '@kol/shared';

/**
 * Podium / big-group filter state.
 *
 * Zustand rather than Redux, per the agreed split: this is ephemeral per-view UI
 * state. Nothing here is server data (that lives in TanStack Query) and none of
 * it needs to outlive the page.
 */
interface ReportFiltersState {
  /** Top-level group filter; only shown when the campaign uses two levels. */
  bigGroup: string;
  /** Podium category filter. */
  category: string;
  /** Podium platform filter. */
  platform: string;
  /** Podium ranking metric. */
  metric: ReportMetric;

  setBigGroup: (value: string) => void;
  setCategory: (value: string) => void;
  setPlatform: (value: string) => void;
  setMetric: (value: ReportMetric) => void;
  /** Called when switching campaigns so stale filters don't leak across. */
  reset: () => void;
}

const initial = {
  bigGroup: FILTER_ALL,
  category: FILTER_ALL,
  platform: FILTER_ALL,
  metric: 'views' as ReportMetric,
};

export const useReportFilters = create<ReportFiltersState>((set) => ({
  ...initial,
  setBigGroup: (bigGroup) => set({ bigGroup }),
  setCategory: (category) => set({ category }),
  setPlatform: (platform) => set({ platform }),
  setMetric: (metric) => set({ metric }),
  reset: () => set(initial),
}));
