import { create } from 'zustand';

/**
 * Toast notifications — ephemeral view state, so this is Zustand's job rather
 * than Redux's (server data stays in TanStack Query). Replaces the legacy
 * `toast()` helper that mutated a fixed `#toast` div.
 */
export interface Toast {
  id: number;
  message: string;
  ok: boolean;
}

/** The legacy toast auto-dismissed after 2.6s. */
const TOAST_DURATION_MS = 2600;

interface ToastState {
  toasts: Toast[];
  show: (message: string, ok?: boolean) => void;
  dismiss: (id: number) => void;
}

let nextId = 0;

export const useToastStore = create<ToastState>((set, get) => ({
  toasts: [],

  show: (message, ok = true) => {
    const id = ++nextId;
    set((s) => ({ toasts: [...s.toasts, { id, message, ok }] }));
    setTimeout(() => get().dismiss(id), TOAST_DURATION_MS);
  },

  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));

/** Imperative helper for use outside components (mutation callbacks). */
export const toast = {
  success: (message: string) => useToastStore.getState().show(message, true),
  error: (message: string) => useToastStore.getState().show(message, false),
};
