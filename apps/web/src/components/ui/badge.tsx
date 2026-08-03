import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '@/lib/utils';

/**
 * `pill` is the legacy `.chip`: a solid rounded-full tag whose colour is
 * data-driven (category colour / platform brand colour) and therefore passed
 * inline by the caller rather than chosen here.
 */
const badgeVariants = cva(
  'inline-flex items-center rounded-full text-[0.7rem] font-semibold leading-tight',
  {
    variants: {
      variant: {
        pill: 'px-2 py-0.5 text-white',
        soft: 'bg-slate-100 px-2 py-1 text-slate-600',
        outline: 'border border-border px-2 py-0.5 text-slate-600',
      },
    },
    defaultVariants: {
      variant: 'pill',
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
