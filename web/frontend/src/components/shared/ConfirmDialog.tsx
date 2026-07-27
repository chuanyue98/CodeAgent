import { useEffect, useRef } from 'react';
import { AlertTriangle } from 'lucide-react';
import Modal from './Modal';

interface ConfirmDialogProps {
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Styles the confirm button as a destructive (red) action. Defaults to true. */
  destructive?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Replaces window.confirm() for actions with real consequences. Unlike the
 * browser dialog, it can say what's actually being removed and doesn't block
 * the render thread, so it matches the rest of the app's visual language.
 */
export default function ConfirmDialog({
  title,
  description,
  confirmLabel = 'Delete',
  cancelLabel = 'Cancel',
  destructive = true,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    confirmRef.current?.focus();
  }, []);

  return (
    <Modal
      onClose={onCancel}
      ariaLabelledBy="confirm-dialog-title"
      ariaDescribedBy="confirm-dialog-description"
      role="alertdialog"
      overlayClassName="pt-[20vh]"
      panelClassName="max-w-sm p-6 space-y-4"
    >
      <div className="flex items-start gap-3">
        <span
          className={`shrink-0 rounded-full p-2 ${
            destructive ? 'bg-red-50 text-red-500' : 'bg-primary/10 text-primary'
          }`}
        >
          <AlertTriangle className="h-4 w-4" />
        </span>
        <div className="min-w-0">
          <h2 id="confirm-dialog-title" className="text-sm font-semibold text-slate-800">
            {title}
          </h2>
          <p id="confirm-dialog-description" className="mt-1 text-sm text-slate-500">
            {description}
          </p>
        </div>
      </div>

      <div className="flex justify-end gap-3 pt-1">
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 border border-slate-200 text-slate-600 rounded-xl text-sm font-medium hover:bg-slate-50 transition-colors"
        >
          {cancelLabel}
        </button>
        <button
          ref={confirmRef}
          type="button"
          onClick={onConfirm}
          className={`px-4 py-2 rounded-xl text-sm font-semibold text-white transition-colors ${
            destructive ? 'bg-red-500 hover:bg-red-600' : 'bg-primary hover:opacity-90'
          }`}
        >
          {confirmLabel}
        </button>
      </div>
    </Modal>
  );
}
