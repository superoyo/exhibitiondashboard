import { configureStore } from '@reduxjs/toolkit';
import { useDispatch, useSelector } from 'react-redux';

import { authReducer } from '@/features/auth/store/authSlice';

/**
 * Global *client* state only. The split, so no two tools own the same data:
 *   - TanStack Query  — all server data (nothing from the API lands here)
 *   - Redux Toolkit   — cross-cutting client session: auth, and later theme
 *   - Zustand         — ephemeral per-view UI (report filters, table sort)
 */
export const store = configureStore({
  reducer: {
    auth: authReducer,
  },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;

export const useAppDispatch = useDispatch.withTypes<AppDispatch>();
export const useAppSelector = useSelector.withTypes<RootState>();
