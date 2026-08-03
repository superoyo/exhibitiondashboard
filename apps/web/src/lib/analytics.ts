import { env } from '@/config/env';

/**
 * Google Analytics, loaded once at boot. Replaces the gtag snippet that was
 * copy-pasted into the <head> of all six legacy pages.
 *
 * A missing measurement id disables analytics entirely rather than sending
 * events to a non-existent property.
 */
export function initAnalytics(): void {
  if (!env.gaId || typeof window === 'undefined') return;
  if (document.querySelector('script[data-ga]')) return;

  const script = document.createElement('script');
  script.async = true;
  script.src = `https://www.googletagmanager.com/gtag/js?id=${env.gaId}`;
  script.dataset.ga = 'true';
  document.head.appendChild(script);

  window.dataLayer = window.dataLayer ?? [];
  function gtag(...args: unknown[]) {
    window.dataLayer?.push(args);
  }
  gtag('js', new Date());
  gtag('config', env.gaId);
}
