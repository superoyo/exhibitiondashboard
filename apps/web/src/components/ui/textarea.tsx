import * as React from 'react';

import { cn } from '@/lib/utils';

/** Secret-entry fields are monospace, like the legacy `.inp` class. */
const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea
    ref={ref}
    className={cn(
      'flex w-full rounded-lg border border-border bg-white px-3 py-2 font-mono text-sm transition-colors',
      'placeholder:font-sans placeholder:text-muted-foreground',
      'focus-visible:border-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand',
      'disabled:cursor-not-allowed disabled:opacity-60',
      className,
    )}
    {...props}
  />
));
Textarea.displayName = 'Textarea';

export { Textarea };
