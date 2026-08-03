import { env } from '@/config/env';

/**
 * TikTok/Facebook CDN image URLs expire within hours. Every avatar and post
 * thumbnail must go through the backend's caching proxy or reports break
 * retroactively — the original pages did this via the `IMG()` helper.
 */
export function proxiedImage(url: string | null | undefined): string {
  if (!url) return '';
  return `${env.apiBaseUrl}/api/img?u=${encodeURIComponent(url)}`;
}
