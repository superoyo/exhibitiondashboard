import { useEffect } from 'react';

import { env } from '@/config/env';

/**
 * Mount point for the shared "Global Menu" widget owned by the host app. The
 * external script looks for a `[data-global-menu]` element and fills it in, so
 * the contract is the attribute — not anything we render inside.
 *
 * Loaded once per session; the script is not re-added on navigation.
 */
export function GlobalMenuSlot() {
  useEffect(() => {
    if (!env.globalMenuUrl) return;
    if (document.querySelector(`script[src="${env.globalMenuUrl}"]`)) return;

    const script = document.createElement('script');
    script.src = env.globalMenuUrl;
    script.defer = true;
    document.body.appendChild(script);
  }, []);

  if (!env.globalMenuUrl) return null;
  return <span data-global-menu className="mr-2.5" />;
}
