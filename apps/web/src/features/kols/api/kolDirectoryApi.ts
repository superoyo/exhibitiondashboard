import type { Platform } from '@kol/shared';

import { api } from '@/lib/axios';

/** One campaign a KOL worked on, with that campaign's totals for them. */
export interface KolCampaignEntry {
  key: string;
  name: string;
  emoji: string;
  category: string | null;
  posts: number;
  views: number;
  likes: number;
  comments: number;
  shares: number;
  saves: number;
  platforms: Platform[];
  /** ISO timestamp of their latest post in that campaign, or null. */
  last_posted: string | null;
}

/** A row of `GET /api/kol-directory` — one KOL across every campaign. */
export interface KolDirectoryEntry {
  username: string;
  display: string;
  avatar: string | null;
  followers: number;
  campaign_count: number;
  posts: number;
  views: number;
  likes: number;
  comments: number;
  shares: number;
  saves: number;
  platforms: Platform[];
  last_posted: string | null;
  campaigns: KolCampaignEntry[];
}

export async function getKolDirectory(): Promise<KolDirectoryEntry[]> {
  const { data } = await api.get<{ kols: KolDirectoryEntry[]; total: number }>('/kol-directory');
  return data.kols ?? [];
}
