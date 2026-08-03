import { useMutation } from '@tanstack/react-query';
import { AxiosError } from 'axios';
import type { LoginInput, LoginResponse } from '@kol/shared';

import { useAppDispatch } from '@/app/store';
import { fetchProfile, login } from '@/features/auth/api/authApi';
import { buildSession } from '@/features/auth/lib/session';
import { signedIn } from '@/features/auth/store/authSlice';

/** Copy matches the legacy login page exactly. */
const BAD_CREDENTIALS = 'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง';
const LOGIN_FAILED = 'เข้าสู่ระบบไม่สำเร็จ กรุณาลองใหม่อีกครั้ง';
const NETWORK_FAILED = 'เชื่อมต่อไม่ได้ กรุณาลองใหม่อีกครั้ง';

export function useLogin() {
  const dispatch = useAppDispatch();

  return useMutation({
    mutationFn: async (input: LoginInput) => {
      let result: LoginResponse;
      try {
        result = await login(input);
      } catch (error) {
        if (error instanceof AxiosError) {
          if (error.response?.status === 401) throw new Error(BAD_CREDENTIALS);
          if (error.code === 'ERR_NETWORK') throw new Error(NETWORK_FAILED);
        }
        throw new Error(LOGIN_FAILED);
      }

      if (!result.access_token) throw new Error(LOGIN_FAILED);

      // Enrich with the full profile: real Thai name + employee photo. A
      // failure here must not block sign-in — the login payload already has
      // enough to render, so we fall back to it.
      let session = buildSession(result);
      try {
        const profile = await fetchProfile(result.access_token);
        session = buildSession(result, profile.profile ?? {});
      } catch {
        // keep the login-only session
      }

      dispatch(signedIn(session));
      return session;
    },
  });
}
