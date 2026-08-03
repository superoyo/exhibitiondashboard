import { useEffect, useState } from 'react';

/** Debounced mirror of a value. Default matches the legacy search delay. */
export function useDebounce<T>(value: T, delayMs = 180): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}
