/**
 * Every path in one place. The legacy URLs are load-bearing: reports have been
 * shared with clients by link, so `/report`, `/sahagroup`, `/sahagroup2027` and
 * `/tracker` must keep resolving forever.
 */
export const routes = {
  home: '/',
  login: '/login',
  tracker: '/tracker',
  roster: '/kols',
  kolList: '/kol-list',
  settings: '/token',

  campaign: (key: string) => `/c/${encodeURIComponent(key)}`,
  campaignPattern: '/c/:campaignKey',

  /** Public client links — random token, never the campaign key. */
  view: (token: string) => `/v/${encodeURIComponent(token)}`,
  viewPattern: '/v/:viewToken',
  viewNamedPattern: '/v/:slug/:viewToken',

  /**
   * Public INFLUENCER links. Same tokens as /v/ but a separate namespace, so
   * the influencer-facing layout can change without touching client links.
   */
  influencerView: (token: string) => `/vi/${encodeURIComponent(token)}`,
  influencerViewPattern: '/vi/:viewToken',
  influencerViewNamedPattern: '/vi/:slug/:viewToken',
} as const;

/** Legacy single-campaign aliases kept alive as redirects. */
export const legacyCampaignAliases: Record<string, string> = {
  '/report': 'pao',
  '/sahagroup': 'sahagroup',
  '/sahagroup2027': 'sahagroup2027',
};

/**
 * Paths that must render without a session. Mirrors the server-side open-path
 * allowlist; getting this wrong breaks every client link.
 */
export function isPublicPath(pathname: string, search = ''): boolean {
  // /v/ (client) and /vi/ (influencer) are both public — matching only /v/
  // would put a login wall in front of every influencer link.
  if (/^\/vi?\//i.test(pathname)) return true;
  if (pathname === routes.login) return true;
  return new URLSearchParams(search).get('view') === '1';
}
