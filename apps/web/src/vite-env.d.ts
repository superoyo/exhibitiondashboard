/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_GA_ID?: string;
  readonly VITE_GLOBAL_MENU_URL?: string;
  /** Dev only — origin that still serves the not-yet-migrated pages. */
  readonly VITE_PROXY_TARGET?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

/** Injected server-side for /v/:token pages so the JS knows its campaign. */
interface Window {
  __CAMPAIGN__?: string;
  dataLayer?: unknown[];
}
