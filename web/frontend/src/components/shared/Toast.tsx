import { AlertCircle, X } from 'lucide-react';

interface ToastProps {
  message: string;
  onDismiss?: () => void;
}

/**
 * Transient failure notice, anchored bottom-right.
 *
 * Every gallery previously inlined its own copy of this markup, none of which
 * could be dismissed — a failed toggle left a red box pinned over the page
 * until navigation. One component, `role="alert"` so screen readers announce
 * it, and an explicit close.
 */
export default function Toast({ message, onDismiss }: ToastProps) {
  return (
    <div
      role="alert"
      className="fixed bottom-4 right-4 z-50 flex max-w-sm items-start gap-2 rounded-xl border border-red-200 bg-red-50 p-4 text-sm font-medium text-red-600 shadow-lg"
    >
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
      <span className="min-w-0 break-words">{message}</span>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="关闭通知"
          className="-mr-1 -mt-1 shrink-0 rounded-md p-1 text-red-400 transition-colors hover:bg-red-100 hover:text-red-700"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}
