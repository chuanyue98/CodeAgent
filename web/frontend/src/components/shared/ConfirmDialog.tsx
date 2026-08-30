import { useEffect, useRef } from 'react';
import { AlertTriangle } from 'lucide-react';
import Modal from './Modal';
import Button from './Button';
import { useT } from '../../i18n/context';

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
  confirmLabel,
  cancelLabel,
  destructive = true,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const t = useT();
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
            destructive ? 'bg-destructive/10 text-destructive' : 'bg-primary/10 text-primary'
          }`}
        >
          <AlertTriangle className="h-4 w-4" />
        </span>
        <div className="min-w-0">
          <h2 id="confirm-dialog-title" className="text-sm font-semibold text-foreground">
            {title}
          </h2>
          <p id="confirm-dialog-description" className="mt-1 text-sm text-muted-foreground">
            {description}
          </p>
        </div>
      </div>

      <div className="flex justify-end gap-3 pt-1">
        <Button type="button" variant="outline" size="lg" onClick={onCancel}>
          {cancelLabel ?? t('common.cancel')}
        </Button>
        <button
          ref={confirmRef}
          type="button"
          onClick={onConfirm}
          className={`px-4 py-2 rounded-lg text-sm font-semibold transition-colors ${
            destructive
              ? 'bg-destructive text-destructive-foreground hover:bg-destructive/90'
              : 'bg-primary text-primary-foreground hover:bg-primary/90'
          }`}
        >
          {confirmLabel ?? t('common.delete')}
        </button>
      </div>
    </Modal>
  );
}
