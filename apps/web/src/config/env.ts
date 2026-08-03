/**
 * Build-time public config. Everything here is compiled into the bundle and
 * visible to users — secrets must never be routed through `import.meta.env`.
 */
export const env = {
  /** '' means same-origin: production, and dev through the Vite proxy. */
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? '',

  /** Unset disables analytics rather than sending to a bogus property. */
  gaId: import.meta.env.VITE_GA_ID ?? '',

  /** Host-app navbar widget; unset simply renders no slot. */
  globalMenuUrl: import.meta.env.VITE_GLOBAL_MENU_URL ?? '',

  isDev: import.meta.env.DEV,
} as const;
