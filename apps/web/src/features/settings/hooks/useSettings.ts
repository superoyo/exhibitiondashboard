import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { queryKeys } from '@/app/queryClient';
import {
  getAiKey,
  getAiStatus,
  getApifyToken,
  saveAiKey,
  saveApifyToken,
  testApifyToken,
} from '@/features/settings/api/settingsApi';

export function useApifyToken() {
  return useQuery({
    queryKey: queryKeys.settings.apifyToken,
    queryFn: getApifyToken,
  });
}

export function useSaveApifyToken() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: saveApifyToken,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.settings.apifyToken }),
  });
}

export function useTestApifyToken() {
  return useMutation({ mutationFn: testApifyToken });
}

export function useAiKey() {
  return useQuery({
    queryKey: queryKeys.settings.aiKey,
    queryFn: getAiKey,
  });
}

export function useAiStatus() {
  return useQuery({
    queryKey: queryKeys.settings.aiStatus,
    // The unforced status is cached server-side; a manual re-check passes force.
    queryFn: () => getAiStatus(false),
  });
}

export function useSaveAiKey() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: saveAiKey,
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.settings.aiKey });
      // The save response already carries a fresh live check — seed it rather
      // than firing another (rate-limited, billable) status call.
      if (result.check) queryClient.setQueryData(queryKeys.settings.aiStatus, result.check);
      else void queryClient.invalidateQueries({ queryKey: queryKeys.settings.aiStatus });
    },
  });
}

/** Manual "ตรวจสอบใหม่" — forces a live re-check, bypassing the server cache. */
export function useRecheckAiStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => getAiStatus(true),
    onSuccess: (status) => queryClient.setQueryData(queryKeys.settings.aiStatus, status),
  });
}
