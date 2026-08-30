import type { ReactNode } from 'react';
import { eb } from '../analytics/present';

type Size = 'sm' | 'md';

interface BadgeProps {
  /** `engine` colors via the shared engine palette (present.ts); `neutral`
      is the gray fallback everything used before. */
  variant?: 'engine' | 'neutral';
  /** Engine key (claude/codex/...); required when variant="engine". */
  engine?: string;
  size?: Size;
  className?: string;
  children: ReactNode;
}

/** Pill badge. Engine identity is rendered exactly once app-wide through
    present.ts's `eb()` — hand-rolled engine badges drift colors (that is how
    MCP's badge ended up cyan while every other page shows sky). */
export default function Badge({
  variant = 'neutral',
  engine,
  size = 'md',
  className = '',
  children,
}: BadgeProps) {
  const color = variant === 'engine' ? eb(engine ?? '') : 'bg-muted text-muted-foreground';
  const sizing = size === 'sm' ? 'px-1.5 py-0.5 text-[9px]' : 'px-2 py-0.5 text-[10px]';
  return (
    <span className={`inline-flex shrink-0 items-center rounded-full font-bold uppercase ${color} ${sizing} ${className}`}>
      {children}
    </span>
  );
}
