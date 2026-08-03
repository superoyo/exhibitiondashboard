import { useEffect, type ReactNode } from 'react';
import { Provider as ReduxProvider } from 'react-redux';
import { QueryClientProvider } from '@tanstack/react-query';

import { queryClient } from '@/app/queryClient';
import { store, useAppDispatch } from '@/app/store';
import { resynced } from '@/features/auth/store/authSlice';
import { SESSION_KEY } from '@/features/auth/lib/session';

/**
 * Keeps this tab honest when another tab signs in or out. Without it, one tab
 * can hold a stale session in Redux and keep rendering a signed-in navbar while
 * every API call 401s.
 */
function SessionSync({ children }: { children: ReactNode }) {
  const dispatch = useAppDispatch();

  useEffect(() => {
    function onStorage(event: StorageEvent) {
      if (event.key === SESSION_KEY) dispatch(resynced());
    }
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, [dispatch]);

  return children;
}

export function Providers({ children }: { children: ReactNode }) {
  return (
    <ReduxProvider store={store}>
      <QueryClientProvider client={queryClient}>
        <SessionSync>{children}</SessionSync>
      </QueryClientProvider>
    </ReduxProvider>
  );
}
