import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import App from './App';
import { store } from '@/app/store';
import { initAnalytics } from '@/lib/analytics';
import { resolveSession } from '@/features/auth/lib/ssoHandoff';
import { sessionResolved } from '@/features/auth/store/authSlice';

import '@/styles/globals.css';

/**
 * The SSO handoff is resolved BEFORE the first render, on purpose.
 *
 * A token can arrive as `#token=…` from a sibling app, and it has to be
 * validated and stored before any component fires a query — otherwise those
 * first requests go out unauthenticated, come back 401, and the guard bounces
 * a user who was in fact signed in. The legacy code achieved the same ordering
 * by wrapping `window.fetch` before its first `await`.
 */
async function bootstrap() {
  initAnalytics();

  const session = await resolveSession();
  store.dispatch(sessionResolved(session));

  const container = document.getElementById('root');
  if (!container) throw new Error('#root not found');

  createRoot(container).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}

void bootstrap();
