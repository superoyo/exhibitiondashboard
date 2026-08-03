import type { KolLink, Platform } from '@kol/shared';

/**
 * Link classification for roster import.
 *
 * This is a verbatim port of logic that existed TWICE in the legacy frontend —
 * once inline in kols.html and once in import-sync.js. They had drifted only in
 * that the page also tracked debug info, so they are unified here.
 *
 * The regexes and skip-lists are load-bearing: they decide whether a pasted
 * link is a trackable post, a profile page that merely names the KOL, or junk.
 * Changing one quietly changes which rows get scraped (and billed).
 */

const text = (s: string | null | undefined): string => (s ?? '').trim();

/** Any non-social link counts as a website (advertorials etc.). */
export function platformOf(url: string | null | undefined): Platform {
  const u = (url ?? '').toLowerCase();
  if (u.includes('tiktok.com')) return 'tiktok';
  if (u.includes('facebook.com') || u.includes('fb.watch') || u.includes('fb.com'))
    return 'facebook';
  if (u.includes('instagram.com')) return 'instagram';
  if (u.includes('youtube.com') || u.includes('youtu.be')) return 'youtube';
  if (u.includes('x.com') || u.includes('twitter.com')) return 'x';
  if (u.includes('line.me')) return 'line';
  return 'website';
}

/**
 * Path segments that are Facebook/Instagram/X *routes*, not account handles.
 * Without these, `facebook.com/watch/...` would be read as a KOL named "watch".
 */
const FB_SKIP = new Set([
  'story.php',
  'permalink.php',
  'profile.php',
  'watch',
  'reel',
  'share',
  'photo',
  'video',
  'groups',
  'events',
  'media',
  'pages',
  'p',
  'login',
  'login.php',
  'l.php',
  'sharer',
  'sharer.php',
  'home.php',
  'hashtag',
  'help',
  'privacy',
  'policies',
  'people',
  'public',
  'stories',
]);
const IG_SKIP = new Set(['p', 'reel', 'reels', 'tv', 'stories', 'explore', 'accounts']);
const X_SKIP = new Set(['i', 'status', 'home', 'search', 'hashtag', 'intent', 'login']);

/** The posting account's @handle, or '' when the URL does not reveal one. */
export function handleFromUrl(url: string | null | undefined): string {
  const u = text(url);

  const tt = /tiktok\.com\/@([^/?#\s]+)/i.exec(u);
  if (tt?.[1]) return tt[1].toLowerCase();

  const fb = /(?:facebook\.com|fb\.com)\/([^/?#\s]+)/i.exec(u);
  if (fb?.[1]) {
    const h = fb[1].toLowerCase();
    if (!FB_SKIP.has(h)) return h;
  }

  const ig = /instagram\.com\/([^/?#\s]+)/i.exec(u);
  if (ig?.[1]) {
    const h = ig[1].toLowerCase();
    if (!IG_SKIP.has(h)) return h;
  }

  const x = /(?:x\.com|twitter\.com)\/([^/?#\s]+)/i.exec(u);
  if (x?.[1]) {
    const h = x[1].toLowerCase();
    if (!X_SKIP.has(h)) return h;
  }

  const yt = /youtube\.com\/@([^/?#\s]+)/i.exec(u);
  if (yt?.[1]) return yt[1].toLowerCase();

  return '';
}

/**
 * Links that appear in campaign sheets but are not campaign work — shipping
 * addresses (Maps) and response forms.
 */
export const NONWORK_URL =
  /google\.[a-z.]+\/maps|maps\.app\.goo\.gl|goo\.gl\/maps|maps\.google|waze\.com|forms\.gle|docs\.google\.com\/forms/i;

/** Unwrap Facebook login / l.php redirect wrappers to the real destination. */
export function normalizeUrl(url: string): string {
  const m = /facebook\.com\/(?:login[^?]*|l\.php)\?(?:[^#]*&)?(?:next|u)=([^&#]+)/i.exec(url);
  if (m?.[1]) {
    try {
      return decodeURIComponent(m[1]);
    } catch {
      // Malformed escape sequence — keep the original URL.
    }
  }
  return url;
}

/**
 * True when the URL points at a profile/channel rather than a single post.
 * These identify WHO the KOL is but are never kept as trackable post links.
 */
export function isProfileUrl(url: string): boolean {
  switch (platformOf(url)) {
    case 'tiktok':
      return /tiktok\.com\/@[^/?#\s]+\/?([?#]|$)/i.test(url);
    case 'facebook':
      return (
        Boolean(handleFromUrl(url)) &&
        !/(\/posts\/|\/videos\/|\/reel\/|\/watch|story_fbid=|\/permalink\/|\/share\/|fb\.watch)/i.test(
          url,
        )
      );
    case 'instagram':
      return Boolean(handleFromUrl(url)) && !/\/(p|reel|reels|tv)\//i.test(url);
    case 'youtube':
      return /youtube\.com\/(@[^/?#\s]+\/?([?#]|$)|channel\/|c\/|user\/)/i.test(url);
    case 'x':
      return Boolean(handleFromUrl(url)) && !/\/status\//i.test(url);
    default:
      return false;
  }
}

/** The platform-native post id, used for dedupe. '' when not a post URL. */
export function postIdOf(platform: string, url: string): string {
  let m: RegExpExecArray | null = null;
  if (platform === 'tiktok') m = /\/video\/(\d+)/.exec(url);
  else if (platform === 'instagram') m = /\/(?:p|reel|reels|tv)\/([A-Za-z0-9_-]+)/.exec(url);
  else if (platform === 'youtube') m = /(?:shorts\/|v=|youtu\.be\/)([A-Za-z0-9_-]{6,})/.exec(url);
  else if (platform === 'x') m = /\/status\/(\d+)/.exec(url);
  else if (platform === 'facebook')
    m = /(?:\/posts\/|\/videos\/|\/reel\/|story_fbid=|\/permalink\/)([\w.-]+)/.exec(url);
  return m?.[1] ?? '';
}

/**
 * Dedupe key for a link: platform + post id, falling back to the URL without
 * its query string. This is what stops the same post pasted twice with
 * different tracking params from becoming two billable rows.
 */
export function linkDedupeKey(platform: string, url: string): string {
  const id = postIdOf(platform, url);
  const bare = (url.split('?')[0] ?? '').replace(/\/$/, '').toLowerCase();
  return `${platform}:${id || bare}`;
}

/** Turn a URL list into deduped links carrying platform + handle. */
export function dedupeLinks(urls: string[]): KolLink[] {
  const seen = new Set<string>();
  const out: KolLink[] = [];
  for (const url of urls) {
    const platform = platformOf(url);
    const key = linkDedupeKey(platform, url);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ platform, url, handle: handleFromUrl(url) });
  }
  return out;
}

/** Dedupe already-built links (used after short links are resolved). */
export function dedupeExistingLinks(links: KolLink[]): KolLink[] {
  const seen = new Set<string>();
  return links.filter((l) => {
    const key = linkDedupeKey(l.platform, l.url);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

/** Every usable URL inside a blob of text, minus the non-work ones. */
export function urlsIn(value: string): string[] {
  const found = value.match(/https?:\/\/[^\s)]+/gi) ?? [];
  return found
    .map((u) => normalizeUrl(u.replace(/[.,;]+$/, '')))
    .filter((u) => !NONWORK_URL.test(u));
}

/**
 * Loose "does this look like a link" test, used for header detection.
 * Callers pass already-stringified cell text (see `cellText` in workbook.ts).
 */
export function looksUrl(value: string): boolean {
  return /https?:\/\/|www\.|tiktok\.com|facebook\.com|fb\.watch|instagram\.com|youtu/i.test(
    text(value),
  );
}
