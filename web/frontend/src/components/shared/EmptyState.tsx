import type { ReactNode } from 'react';
import { type LucideIcon } from 'lucide-react';

interface EmptyStateProps {
  icon?: LucideIcon;
  title: ReactNode;
  body?: ReactNode;
  /** Call-to-action row; pass a fragment for multiple buttons. */
  action?: ReactNode;
  /** Compact renders as a single quiet line for secondary lists (search
      misses inside a panel); full is the card treatment for primary views. */
  compact?: boolean;
  className?: string;
}

/**
 * The one empty state. TaskList's original (icon tile + title + body + CTA)
 * is the benchmark this generalizes; six other lists showed only a bare gray
 * sentence, and one page managed two different alignments on the same screen.
 */
export default function EmptyState({
  icon: Icon,
  title,
  body,
  action,
  compact = false,
  className = '',
}: EmptyStateProps) {
  if (compact) {
    return (
      <div className={`flex flex-col items-center gap-1.5 py-8 text-center ${className}`}>
        {Icon && <Icon className="h-4 w-4 text-muted-foreground/60" aria-hidden />}
        <p className="text-xs text-muted-foreground">{title}</p>
        {body && <p className="text-xs text-muted-foreground">{body}</p>}
      </div>
    );
  }
  return (
    <div className={`glass-card flex flex-col items-center gap-3 px-6 py-12 text-center ${className}`}>
      {Icon && (
        <div className="rounded-2xl bg-primary/10 p-3 text-primary">
          <Icon className="h-6 w-6" aria-hidden />
        </div>
      )}
      <div className="max-w-md space-y-1.5">
        <p className="text-sm font-semibold text-foreground">{title}</p>
        {body && <p className="text-xs leading-5 text-muted-foreground">{body}</p>}
      </div>
      {action && (
        <div className="flex flex-wrap items-center justify-center gap-2 pt-1">{action}</div>
      )}
    </div>
  );
}
