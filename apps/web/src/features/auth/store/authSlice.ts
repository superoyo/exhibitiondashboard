import { createSlice, type PayloadAction } from '@reduxjs/toolkit';
import type { Session } from '@kol/shared';

import { clearSession, readSession, writeSession } from '../lib/session';

/**
 * Redux Toolkit owns the *client* session — who is signed in, for rendering.
 * localStorage stays the source of truth for the token itself (the Axios
 * interceptor reads it there), so this slice mirrors rather than replaces it.
 *
 * Server data never lives here; that is TanStack Query's job.
 */
interface AuthState {
  session: Session | null;
  /** False until the SSO handoff has been resolved once. */
  ready: boolean;
}

const initialState: AuthState = {
  session: null,
  ready: false,
};

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    /** Called once at boot with whatever the handoff/localStorage resolved to. */
    sessionResolved(state, action: PayloadAction<Session | null>) {
      state.session = action.payload;
      state.ready = true;
    },
    signedIn(state, action: PayloadAction<Session>) {
      writeSession(action.payload);
      state.session = action.payload;
      state.ready = true;
    },
    signedOut(state) {
      clearSession();
      state.session = null;
      state.ready = true;
    },
    /** Re-read localStorage — used when another tab changes the session. */
    resynced(state) {
      state.session = readSession();
    },
  },
});

export const { sessionResolved, signedIn, signedOut, resynced } = authSlice.actions;
export const authReducer = authSlice.reducer;
