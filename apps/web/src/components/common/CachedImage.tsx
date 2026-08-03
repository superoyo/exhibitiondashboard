import { useState } from 'react';

import { proxiedImage } from '@/lib/imageProxy';
import { cn } from '@/lib/utils';

/**
 * Image routed through the backend's caching proxy.
 *
 * TikTok/Facebook CDN URLs are signed and expire within days, so a direct
 * `<img src>` would leave old reports full of broken images. On error the
 * element hides itself rather than showing a broken-image icon — the same
 * behaviour the legacy `onerror` handlers gave.
 */
export function CachedImage({
  src,
  alt = '',
  className,
  style,
}: {
  src: string | null | undefined;
  alt?: string;
  className?: string;
  style?: React.CSSProperties;
}) {
  const [failed, setFailed] = useState(false);
  if (!src || failed) return null;

  return (
    <img
      src={proxiedImage(src)}
      alt={alt}
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
      className={cn(className)}
      style={style}
    />
  );
}
