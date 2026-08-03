import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { loginInputSchema } from '@kol/shared';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Logo } from '@/components/layout/Logo';
import { useAppSelector } from '@/app/store';
import { safeNextUrl } from '@/features/auth/lib/session';
import { useLogin } from '@/features/auth/hooks/useLogin';

export default function LoginPage() {
  const location = useLocation();
  const session = useAppSelector((s) => s.auth.session);
  const { mutate: signIn, isPending } = useLogin();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const next = safeNextUrl(location.search);

  // Already signed in — go straight through. A full navigation rather than a
  // router push, so `next` can point at a legacy path served outside React.
  useEffect(() => {
    if (session) window.location.replace(next);
  }, [session, next]);

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');

    const parsed = loginInputSchema.safeParse({ username, password });
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? '');
      return;
    }

    signIn(parsed.data, {
      onSuccess: () => window.location.replace(next),
      onError: (err: Error) => setError(err.message),
    });
  }

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="m-4 w-full max-w-[380px] rounded-2xl border border-border bg-white p-8 shadow-card-lg">
        <h1 className="mb-1 text-xl font-bold">
          <Logo asLink={false} />
        </h1>
        <p className="mb-6 text-[0.85rem] text-muted-foreground">
          เข้าสู่ระบบด้วยบัญชีพนักงาน (Wazzup)
        </p>

        <form onSubmit={handleSubmit} noValidate>
          <Label htmlFor="username">ชื่อผู้ใช้</Label>
          <Input
            id="username"
            autoComplete="username"
            autoFocus
            required
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="mb-4"
          />

          <Label htmlFor="password">รหัสผ่าน</Label>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mb-4"
          />

          <Button type="submit" size="lg" disabled={isPending} className="w-full rounded-[10px]">
            {isPending ? 'กำลังเข้าสู่ระบบ…' : 'เข้าสู่ระบบ'}
          </Button>

          <p role="alert" className="mt-3 min-h-[1.2em] text-[0.85rem] text-destructive">
            {error}
          </p>
        </form>
      </div>
    </div>
  );
}
