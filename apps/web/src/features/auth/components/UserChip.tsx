import { useEffect, useRef, useState } from 'react';
import { LogOut } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { useAppDispatch, useAppSelector } from '@/app/store';
import { signedOut } from '@/features/auth/store/authSlice';
import { routes } from '@/config/routes';

import { UserAvatar } from './UserAvatar';

/**
 * Avatar button in the navbar that opens a small account popup (full name,
 * position, sign out). Nothing but the avatar shows in the nav itself, to keep
 * it tidy on mobile.
 */
export function UserChip() {
  const session = useAppSelector((s) => s.auth.session);
  const dispatch = useAppDispatch();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: MouseEvent) {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false);
    }
    document.addEventListener('click', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('click', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  if (!session) return null;

  const name =
    session.displayName ||
    session.empThaiName ||
    session.empEngName ||
    session.nickName ||
    session.email ||
    '';

  function handleSignOut() {
    dispatch(signedOut());
    // Full navigation, not a router push: this clears every cached query and
    // any in-flight request tied to the old session.
    window.location.href = routes.login;
  }

  return (
    <div ref={wrapRef} className="relative ml-auto">
      <button
        type="button"
        aria-label={`บัญชี ${name}`}
        aria-haspopup="true"
        aria-expanded={open}
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        className="relative rounded-full leading-none transition-shadow hover:shadow-[0_0_0_3px_#eef2f7]"
      >
        <UserAvatar name={name} photo={session.photo} size={36} />
        <span
          aria-hidden="true"
          className="absolute -bottom-0.5 -right-0.5 flex size-3.5 items-center justify-center rounded-full border-2 border-white bg-slate-400 font-display text-[0.55rem] leading-none text-white shadow-sm"
        >
          ▾
        </span>
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-[calc(100%+10px)] z-[60] w-[280px] rounded-xl border border-border bg-white p-4 shadow-popup"
        >
          <div className="flex min-w-0 items-center gap-3">
            <UserAvatar name={name} photo={session.photo} size={56} />
            <div className="min-w-0 flex-1">
              <div className="break-words text-[0.95rem] font-bold leading-tight text-foreground">
                {session.empThaiName || name || '(ไม่มีชื่อ)'}
              </div>
              {session.positionName && (
                <div className="mt-0.5 break-words text-[0.78rem] leading-snug text-muted-foreground">
                  {session.positionName}
                </div>
              )}
            </div>
          </div>

          <div className="my-3.5 h-px bg-border" />

          <Button
            type="button"
            role="menuitem"
            variant="outline"
            onClick={handleSignOut}
            className="w-full hover:border-red-200 hover:bg-red-50 hover:text-destructive"
          >
            <LogOut aria-hidden="true" />
            <span>ออกจากระบบ</span>
          </Button>
        </div>
      )}
    </div>
  );
}
