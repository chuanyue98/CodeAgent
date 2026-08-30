import { AlertCircle, X } from 'lucide-react';
import { useT } from '../../i18n/context';

interface ErrorBarProps {
  message: string;
  /** Inline retry for transient failures; renders as a text link. */
  onRetry?: () => void;
  onDismiss?: () => void;
}

/**
 * Inline failure notice for a failed action or fetch. Four hand-rolled error
 * strips with four token sets (red-200/red-50, destructive/20, and two
 * ad-hoc mixes) collapsed into the destructive tokens, which is what a dark
 * theme will restyle. Page-level load failures with a retry belong to
 * ErrorState; this is for everything shorter.
 */
export default function ErrorBar({ message, onRetry, onDismiss }: ErrorBarProps) {
  const t = useT();
  return (
    <div
      role="alert"
      className="animate-fade-in flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive"
    >
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <span className="min-w-0 flex-1 break-words">{message}</span>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="shrink-0 font-medium underline-offset-2 hover:underline"
        >
          {t('common.retry')}
        </button>
      )}
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label={t('toast.dismiss')}
          className="-mr-1 -mt-1 shrink-0 rounded-md p-1 text-destructive/70 transition-colors hover:bg-destructive/10 hover:text-destructive"
        >
          <X className="h-3.5 w-3.5" aria-hidden />
        </button>
      )}
    </div>
  );
}
