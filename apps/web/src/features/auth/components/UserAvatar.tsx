import { useState } from 'react';

import { cn } from '@/lib/utils';

/** First + last initial, or the leading character for a single-word name. */
export function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    const first = parts[0]?.[0] ?? '';
    const last = parts[parts.length - 1]?.[0] ?? '';
    return (first + last).toUpperCase();
  }
  return (parts[0] ?? '?').slice(0, 1).toUpperCase();
}

/**
 * Deterministic colour per name, so a given person keeps the same avatar tint
 * across sessions and devices.
 */
export function avatarColorOf(name: string): string {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) & 0xffff;
  return `hsl(${h % 360},55%,42%)`;
}

interface UserAvatarProps {
  name: string;
  photo?: string;
  size: number;
  className?: string;
}

/**
 * Initials underneath, photo layered on top. If the photo 404s it unmounts and
 * the initials show through — same fallback the legacy `img.onerror` gave us.
 */
export function UserAvatar({ name, photo, size, className }: UserAvatarProps) {
  const [photoFailed, setPhotoFailed] = useState(false);
  const showPhoto = Boolean(photo) && !photoFailed;

  return (
    <div
      className={cn('relative flex-none', className)}
      style={{ width: size, height: size, fontSize: size * 0.36 }}
    >
      <div
        className="absolute inset-0 flex items-center justify-center rounded-full border border-border font-display font-bold tracking-[0.02em] text-white"
        style={{ background: avatarColorOf(name) }}
      >
        {initialsOf(name)}
      </div>
      {showPhoto && (
        <img
          src={photo}
          alt={name}
          referrerPolicy="no-referrer"
          onError={() => setPhotoFailed(true)}
          className="absolute inset-0 size-full rounded-full border border-border bg-slate-200 object-cover"
        />
      )}
    </div>
  );
}
