import { useCallback, useEffect, useState } from 'react';

/**
 * The Tracker's KOL detail view has always lived at `#/kol/<username>`, and
 * those links are bookmarkable/shareable. React Router's BrowserRouter ignores
 * the hash, so the fragment is read directly here rather than moving the detail
 * view to a new path — that would break every existing link.
 */
const PREFIX = '#/kol/';

function readHash(): string | null {
  const hash = window.location.hash;
  if (!hash.startsWith(PREFIX)) return null;
  const raw = hash.slice(PREFIX.length);
  if (!raw) return null;
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

export function useHashKol() {
  const [username, setUsername] = useState<string | null>(readHash);

  useEffect(() => {
    const onHashChange = () => setUsername(readHash());
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  const open = useCallback((name: string) => {
    window.location.hash = `/kol/${encodeURIComponent(name)}`;
    window.scrollTo(0, 0);
  }, []);

  const close = useCallback(() => {
    window.location.hash = '';
  }, []);

  return { username, open, close };
}
